"""OpenCodeServeBackend — LLMBackend that routes through `opencode serve`."""

from __future__ import annotations

import contextlib
import json
import re
import subprocess
import threading
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from mirach import config, i18n
from mirach.harness.events import (
    AwaitingConfirmationEvent,
    ConversationBus,
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from mirach.harness.policy.engine import Decision, PolicyEngine
from mirach.llm_types import LLMResult, _strip_markdown
from mirach.logging_setup import log

_STRATEGIES_WITH_COMPACT = {"summarize"}

if TYPE_CHECKING:
    pass

_CONFIRM_TIMEOUT = 60.0  # seconds to wait for user CONFIRM reply


class OpenCodeServeBackend:
    """
    LLMBackend that delegates to opencode serve via HTTP + SSE.

    Manages the opencode serve subprocess lifetime, creates/reuses sessions,
    translates the SSE event stream into ConversationBus events, and enforces
    PolicyEngine on every permission request emitted by OpenCode.

    Set MIRACH_BACKEND=opencode_serve to use this backend.
    """

    def __init__(
        self,
        policy: PolicyEngine,
        bus: ConversationBus,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        provider_id: str = "",
        model_id: str = "",
        cwd: str = "",
        startup_timeout: float = 15.0,
    ) -> None:
        self._policy = policy
        self._bus = bus
        self._host = host
        self._port = port
        self._provider_id = provider_id
        self._model_id = model_id
        self._cwd = cwd or str(Path.cwd())
        self._startup_timeout = startup_timeout

        self._base_url: str = ""
        self._proc: subprocess.Popen | None = None
        self._session_id: str | None = None
        self._last_interaction: float = 0.0

        self._interrupted = threading.Event()
        # _sse_resp is set while query() is streaming; interrupt() closes it.
        self._sse_resp: object = None

        self._confirm_event = threading.Event()
        self._confirm_result: bool = True  # True=allow, False=deny

        # Current context size in tokens. opencode serve does not deliver token
        # counts over the SSE stream, so this is refreshed from the REST API
        # (_fetch_session_tokens) after each turn. Zeroed on reset/compact.
        self._session_tokens: int = 0

    # ── subprocess lifecycle ─────────────────────────────────────────────

    def start(self) -> None:
        """Launch opencode serve and wait for it to print its URL on stdout."""
        args = [
            "opencode",
            "serve",
            f"--hostname={self._host}",
            f"--port={self._port}",
        ]
        if config.OPENCODE_SERVE_LOG:
            args.append("--print-logs")
        self._proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.time() + self._startup_timeout
        output_lines: list[str] = []
        while time.time() < deadline:
            line = self._proc.stdout.readline()  # type: ignore[union-attr]
            if not line:
                break
            output_lines.append(line.rstrip())
            if "opencode server listening" in line:
                m = re.search(r"on\s+(https?://\S+)", line)
                if m:
                    self._base_url = m.group(1).rstrip("/")
                    log.info("opencode serve started at %s", self._base_url)
                    self._start_stdout_drain()
                    return
        raise RuntimeError(
            f"opencode serve did not start within {self._startup_timeout}s. Output: {output_lines}"
        )

    def _start_stdout_drain(self) -> None:
        """Drain opencode serve's stdout for the life of the process.

        stdout is a PIPE we stop reading after the startup line. opencode keeps
        logging (every HTTP request + plugins), so without draining, the OS pipe
        buffer (~64KB) fills and opencode blocks on its next write — deadlocking
        the server mid-turn (turns hang / time out). A daemon thread reads and
        discards (debug-logs) the rest so the pipe never fills.
        """

        log_path = config.OPENCODE_SERVE_LOG

        def _drain() -> None:
            sink = None
            with contextlib.suppress(Exception):
                if log_path:
                    sink = open(log_path, "w", buffering=1)  # noqa: SIM115
                for line in self._proc.stdout:  # type: ignore[union-attr]
                    if sink is not None:
                        sink.write(line)
                    else:
                        log.debug("opencode: %s", line.rstrip())
            if sink is not None:
                with contextlib.suppress(Exception):
                    sink.close()

        threading.Thread(target=_drain, daemon=True, name="opencode-stdout-drain").start()

    def stop(self) -> None:
        """Terminate the opencode serve subprocess."""
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        self._base_url = ""

    def _ensure_running(self) -> None:
        """Restart opencode serve if the process has died."""
        if not self._base_url or (self._proc and self._proc.poll() is not None):
            log.warning("opencode serve is not running, restarting...")
            self.stop()
            self.start()

    # ── LLMBackend protocol ──────────────────────────────────────────────

    @property
    def bus(self) -> ConversationBus:
        """The ConversationBus this backend publishes to (shared with the server)."""
        return self._bus

    def confirm(self, tool_call_id: str) -> None:
        """Approve the pending mid-flight confirmation. opencode tracks a single
        pending permission per session, so the id is accepted but not matched."""
        self.reply_confirmation(True)

    def deny(self, tool_call_id: str) -> None:
        """Reject the pending mid-flight confirmation (id accepted, not matched)."""
        self.reply_confirmation(False)

    def query(self, text: str, system_prompt: str, obsidian_context: str = "") -> LLMResult:
        t0 = time.time()
        self._ensure_running()

        new_session = self.session_expired()
        if new_session:
            self.reset_session()

        if self._session_id is None:
            self._session_id = self._create_session()
            log.info("opencode session created: %s", self._session_id)

        self._interrupted.clear()
        self._confirm_event.clear()

        # Build request body
        body: dict = {
            "parts": [{"type": "text", "text": text}],
        }
        if new_session and system_prompt:
            parts = [f"Follow these instructions for the ENTIRE conversation:\n\n{system_prompt}"]
            if obsidian_context:
                parts.append(f"Restored context from your memory:\n\n{obsidian_context}")
            body["system"] = "\n\n---\n\n".join(parts)
        if self._provider_id and self._model_id:
            body["model"] = {"providerID": self._provider_id, "modelID": self._model_id}

        # Open the SSE connection BEFORE sending the prompt so we never miss
        # events (including session.idle) that arrive before the first read().
        params = urlencode({"directory": self._cwd})
        sse_url = f"{self._base_url}/event?{params}"
        sse_req = urllib.request.Request(sse_url, headers={"Accept": "text/event-stream"})

        part_texts: dict[str, str] = {}
        # partID → part type ("text" | "reasoning" | "tool" | ...), learned from
        # message.part.updated. Reasoning parts also stream field=="text" deltas,
        # and must NOT reach the spoken/displayed response.
        part_kinds: dict[str, str] = {}
        # callIDs whose tool_call / tool_result we already published (part.updated
        # re-fires on every state change: pending → running → completed).
        tool_called: set[str] = set()
        tool_resulted: set[str] = set()
        error_msg = ""

        with urllib.request.urlopen(sse_req) as sse_resp:
            self._sse_resp = sse_resp
            try:
                # Prompt fires after SSE is open — no race condition.
                self._http_post(f"/session/{self._session_id}/prompt_async", body)

                for event in _parse_sse(sse_resp, self._interrupted):
                    etype = event.get("type")
                    props = event.get("properties", {})

                    if etype == "message.part.updated":
                        part = props.get("part") or {}
                        part_id = part.get("id", "")
                        if part_id:
                            part_kinds[part_id] = part.get("type", "")
                        if part.get("type") == "tool":
                            self._publish_tool_part(part, tool_called, tool_resulted)

                    elif etype == "message.part.delta":
                        # Each event carries one incremental text chunk.
                        # field=="text" → assistant prose; other fields (e.g. "input") are tool args.
                        if props.get("field") == "text":
                            delta = props.get("delta", "")
                            part_id = props.get("partID", "")
                            # Unknown partID falls back to "text" (losing prose is
                            # worse than leaking a stray reasoning chunk).
                            if part_kinds.get(part_id, "text") == "reasoning":
                                continue
                            part_texts[part_id] = part_texts.get(part_id, "") + delta
                            if delta:
                                self._bus.publish(TextDeltaEvent(delta=delta))

                    elif etype in ("permission.updated", "permission.asked"):
                        self._handle_permission(props)

                    elif etype == "session.idle":
                        if props.get("sessionID", self._session_id) == self._session_id:
                            break

                    elif etype == "session.error":
                        err = props.get("error") or {}
                        if isinstance(err, dict):
                            error_msg = err.get("data", {}).get("message", "unknown error")
                        else:
                            error_msg = str(err)
                        log.error("opencode session error: %s", error_msg)
                        break

                    if self._interrupted.is_set():
                        break

            except Exception as exc:
                if not self._interrupted.is_set():
                    log.exception("Error streaming opencode events: %s", exc)
                    error_msg = str(exc)
            finally:
                self._sse_resp = None

        if self._interrupted.is_set():
            self._bus.publish(DoneEvent(content=""))
            return LLMResult("", new_session, True, time.time() - t0)

        if error_msg:
            self._bus.publish(ErrorEvent(message=error_msg))
            return LLMResult(i18n.t("generic_error"), new_session, False, time.time() - t0)

        # The stream interleaves reasoning and answer deltas, and the part-type
        # metadata (message.part.updated) often arrives after the deltas — so the
        # accumulated text may still contain reasoning. The REST message store is
        # authoritative: fetch the final assistant message and keep only its
        # "text" parts. The streamed accumulation is used only if the REST fetch
        # itself fails (None) — an empty-but-successful fetch means the model
        # produced no answer text, and falling back would leak raw reasoning.
        final_text = self._fetch_final_text()
        full_text = final_text if final_text is not None else "".join(part_texts.values()).strip()
        if not full_text:
            log.warning("opencode serve: empty response")
            self._bus.publish(DoneEvent(content=i18n.t("no_response")))
            return LLMResult(i18n.t("no_response"), new_session, False, time.time() - t0)

        response = _strip_markdown(full_text)
        elapsed = time.time() - t0
        self._last_interaction = time.time()
        self._bus.publish(DoneEvent(content=response))
        log.info("opencode serve responded (%.2fs): %s", elapsed, response[:120])

        # Compact context if the session token budget is exceeded. opencode serve
        # does not emit token counts on the SSE stream (no message.updated events
        # in v1.14.x), so read the authoritative count from the REST API after the
        # turn rather than accumulating from events.
        if config.CONTEXT_STRATEGY in _STRATEGIES_WITH_COMPACT:
            self._session_tokens = self._fetch_session_tokens()
            if self._session_tokens > config.CONTEXT_MAX_TOKENS:
                self._compact()

        return LLMResult(response, new_session, False, elapsed)

    def interrupt(self) -> None:
        self._interrupted.set()
        self._confirm_event.set()  # unblock any waiting CONFIRM
        if self._session_id and self._base_url:
            try:
                self._http_post(f"/session/{self._session_id}/abort", {})
            except Exception as exc:
                log.warning("opencode abort failed: %s", exc)
        if self._sse_resp is not None:
            with contextlib.suppress(Exception):
                self._sse_resp.close()  # type: ignore[union-attr]
        log.info("OpenCodeServeBackend interrupted")

    def session_expired(self) -> bool:
        if self._last_interaction == 0.0:
            return True
        return (time.time() - self._last_interaction) > config.SESSION_IDLE_TIMEOUT

    def reset_session(self) -> None:
        if self._session_id and self._base_url:
            try:
                self._http_delete(f"/session/{self._session_id}")
            except Exception as exc:
                log.warning("Could not delete opencode session: %s", exc)
        self._session_id = None
        self._last_interaction = 0.0
        self._session_tokens = 0
        log.info("opencode session reset")

    def _compact(self) -> None:
        """Trigger server-side context compaction via POST /session/{id}/summarize.

        Endpoint verified from @opencode-ai/sdk v1 (sdk.gen.js):
          POST /session/{id}/summarize
          Body (optional): {providerID, modelID}
          Returns: 200 boolean (true = success)
        """
        if not self._session_id or not self._base_url:
            return
        body: dict = {}
        if self._provider_id and self._model_id:
            body = {"providerID": self._provider_id, "modelID": self._model_id}
        try:
            result = self._http_post(f"/session/{self._session_id}/summarize", body)
            if result is True or result == {} or result:
                self._session_tokens = 0
                log.info("opencode context compacted (session %s)", self._session_id)
            else:
                log.warning("opencode compact returned unexpected result: %r", result)
        except Exception as exc:
            log.warning("opencode compact failed: %s", exc)

    def _fetch_session_tokens(self) -> int:
        """Current context size in tokens = the last assistant message's
        input+output, read from GET /session/{id}/message.

        opencode serve (v1.14.x) does not deliver token counts over the SSE
        stream, so the budget tracker reads them from the REST API after each
        turn. The last assistant message's `input` already reflects the full
        prompt (system + history), so `input + output` approximates the context
        footprint. Returns the previous value on failure so a transient error
        can't silently wipe the budget and trigger a needless compact.
        """
        if not self._session_id or not self._base_url:
            return 0
        try:
            messages = self._http_get(f"/session/{self._session_id}/message")
        except Exception as exc:
            log.warning("could not fetch session tokens: %s", exc)
            return self._session_tokens
        tokens = 0
        for msg in messages if isinstance(messages, list) else []:
            info = msg.get("info", msg) if isinstance(msg, dict) else {}
            if info.get("role") == "assistant":
                tk = info.get("tokens") or {}
                if isinstance(tk, dict):
                    tokens = tk.get("input", 0) + tk.get("output", 0)
        return tokens

    def _fetch_final_text(self) -> str | None:
        """Authoritative answer text for the turn that just finished.

        Reads GET /session/{id}/message and concatenates only the `"text"` parts
        of the last assistant message — reasoning parts (chain-of-thought that
        models like deepseek emit as a separate part) are thereby excluded from
        TTS and the DoneEvent. Returns None on fetch failure (caller may fall
        back to streamed text); returns "" when the fetch succeeded but the
        model produced no answer text (caller must NOT fall back — the streamed
        text would reintroduce the reasoning).
        """
        if not self._session_id or not self._base_url:
            return None
        try:
            messages = self._http_get(f"/session/{self._session_id}/message")
        except Exception as exc:
            log.warning("could not fetch final message: %s", exc)
            return None
        last_assistant: dict | None = None
        for msg in messages if isinstance(messages, list) else []:
            info = msg.get("info", msg) if isinstance(msg, dict) else {}
            if info.get("role") == "assistant":
                last_assistant = msg
        if not last_assistant:
            return None
        texts = [
            p.get("text", "")
            for p in last_assistant.get("parts", [])
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        return "".join(texts).strip()

    def reply_confirmation(self, allow: bool) -> None:
        """Signal a pending CONFIRM permission request from external code."""
        self._confirm_result = allow
        self._confirm_event.set()

    # ── tool part → bus events ───────────────────────────────────────────

    def _publish_tool_part(self, part: dict, called: set, resulted: set) -> None:
        """Translate an opencode tool part state into tool_call/tool_result events.

        part.updated fires on every state change (pending → running → completed/
        error); the `called`/`resulted` sets keep each event published once.
        """
        call_id = part.get("callID") or part.get("id", "")
        state = part.get("state") or {}
        status = state.get("status", "")

        if call_id not in called and status in ("running", "completed", "error"):
            called.add(call_id)
            self._bus.publish(
                ToolCallEvent(
                    id=call_id,
                    name=part.get("tool", ""),
                    arguments=state.get("input") or {},
                )
            )
        if call_id not in resulted and status in ("completed", "error"):
            resulted.add(call_id)
            output = state.get("output") if status == "completed" else state.get("error", "")
            self._bus.publish(
                ToolResultEvent(
                    tool_call_id=call_id,
                    result=str(output or "")[:2000],
                    error=status == "error",
                )
            )

    # ── permission handling ──────────────────────────────────────────────

    def _handle_permission(self, props: dict) -> None:
        """Decide an opencode permission request against the harness policy.

        Accepts both wire formats:
        - legacy `permission.updated`: {id, sessionID, type, pattern, callID, title}
        - v1.14+ `permission.asked` (PermissionRequest): {id, sessionID, permission,
          patterns: [...], metadata, tool: {messageID, callID}}
        """
        perm_id = props.get("id", "")
        session_id = props.get("sessionID") or self._session_id or ""
        tool_type = props.get("type") or props.get("permission", "")
        pattern = props.get("pattern")
        if pattern is None:
            patterns = props.get("patterns") or []
            pattern = patterns[0] if patterns else None
        title = props.get("title", tool_type)
        metadata = props.get("metadata", {}) or {}
        call_id = props.get("callID", "") or (props.get("tool") or {}).get("callID", "")

        # Build args for PolicyEngine from OpenCode permission fields
        if tool_type == "bash":
            args: dict = {"command": pattern if isinstance(pattern, str) else ""}
        elif tool_type in ("edit", "external_directory"):
            args = {"path": pattern if isinstance(pattern, str) else ""}
        elif tool_type == "webfetch":
            args = {"url": pattern if isinstance(pattern, str) else ""}
        else:
            args = {}

        decision = self._policy.check(_opencode_type_to_policy_tool(tool_type), args)

        if decision == Decision.ALLOW:
            self._reply_permission(session_id, perm_id, "once")

        elif decision == Decision.DENY:
            # Make the policy denial visible to clients — otherwise the tool
            # silently fails and the user can't tell why nothing happened.
            self._bus.publish(
                ErrorEvent(message=f"[policy] {tool_type} denied: {pattern or title}")
            )
            self._reply_permission(session_id, perm_id, "reject")

        else:  # CONFIRM
            confirm_args: dict = {"title": title}
            if pattern:
                confirm_args["pattern"] = pattern
            confirm_args.update(metadata)
            self._bus.publish(
                AwaitingConfirmationEvent(
                    tool_call_id=call_id or perm_id,
                    name=tool_type,
                    arguments=confirm_args,
                )
            )
            self._confirm_event.clear()
            self._confirm_result = True
            confirmed = self._confirm_event.wait(timeout=_CONFIRM_TIMEOUT)
            if not confirmed or self._interrupted.is_set():
                self._reply_permission(session_id, perm_id, "reject")
            else:
                self._reply_permission(
                    session_id,
                    perm_id,
                    "once" if self._confirm_result else "reject",
                )

    def _reply_permission(self, session_id: str, perm_id: str, response: str) -> None:
        try:
            self._http_post(
                f"/session/{session_id}/permissions/{perm_id}",
                {"response": response},
            )
            log.info("Permission %s → %s", perm_id, response)
        except Exception as exc:
            log.warning("Permission reply failed: %s", exc)

    # ── HTTP helpers ─────────────────────────────────────────────────────

    def _http_post(self, path: str, body: dict) -> dict:
        params = urlencode({"directory": self._cwd})
        url = f"{self._base_url}{path}?{params}"
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}

    def _http_get(self, path: str):
        params = urlencode({"directory": self._cwd})
        url = f"{self._base_url}{path}?{params}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else []

    def _http_delete(self, path: str) -> None:
        params = urlencode({"directory": self._cwd})
        url = f"{self._base_url}{path}?{params}"
        req = urllib.request.Request(url, method="DELETE")
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            resp.read()

    def _create_session(self) -> str:
        result = self._http_post("/session", {})
        return result["id"]


# ── module-level helpers ──────────────────────────────────────────────────────


def _opencode_type_to_policy_tool(opencode_type: str) -> str:
    """Map OpenCode permission type → PolicyEngine tool name."""
    return {
        "bash": "bash",
        "edit": "edit_file",
        "webfetch": "web_fetch",
        "doom_loop": "bash",
        "external_directory": "read_file",
    }.get(opencode_type, opencode_type)


def _parse_sse(response: object, interrupted: threading.Event) -> Iterator[dict]:
    """
    Parse an SSE stream from an open HTTP response object.

    Yields one dict per SSE event. Stops when the connection closes,
    `interrupted` is set, or `response.read()` raises.
    """
    # read1() returns as soon as ANY bytes are available. A plain read(4096)
    # blocks until the full 4096 bytes accumulate, which stalls short SSE turns
    # for minutes (a whole turn's events are < 1KB) — the response sat unread
    # until enough later events/keepalives filled the buffer. Fall back to
    # read() for file-likes without read1 (e.g. test fakes).
    read_available = getattr(response, "read1", None) or response.read  # type: ignore[union-attr]
    buf = b""
    try:
        while not interrupted.is_set():
            try:
                chunk = read_available(4096)
            except Exception:
                break
            if not chunk:
                break
            buf += chunk
            buf = buf.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            while b"\n\n" in buf:
                msg, buf = buf.split(b"\n\n", 1)
                data_lines = [
                    ln[5:].lstrip(b" ") for ln in msg.split(b"\n") if ln.startswith(b"data:")
                ]
                if data_lines:
                    raw = b"\n".join(data_lines)
                    with contextlib.suppress(json.JSONDecodeError):
                        yield json.loads(raw)
    except Exception:
        pass
