"""OpenCodeServeBackend — LLMBackend that routes through `opencode serve`."""

from __future__ import annotations

import base64
import contextlib
import json
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote, urlencode

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

# Every opencode 2.x route lives under /api.
_API = "/api"

# Verified in the 2.0.5 spike (S8): PUT .../instructions/entries/{key} returns
# 204 and the model obeys the entry. Flip to False to fall back to prefixing the
# system prompt onto the first user message instead.
_USE_INSTRUCTION_ENTRIES = True
_INSTRUCTION_KEY = "mirach-system"

# A turn ends on one of these. A rejected permission also lands here as
# `interrupted` (reason "shutdown"), not as `succeeded`.
_TERMINAL_EVENTS = {
    "session.execution.succeeded",
    "session.execution.failed",
    "session.execution.interrupted",
}

# Sent on every session we create. Session rules are evaluated AFTER the agent's
# own (last match wins), so they force "ask" without depending on opencode.json
# — which is tied to the cwd and therefore does not apply in production.
_SESSION_RULES = [
    {"action": "shell", "resource": "*", "effect": "ask"},
    {"action": "edit", "resource": "*", "effect": "ask"},
    {"action": "webfetch", "resource": "*", "effect": "ask"},
    {"action": "question", "resource": "*", "effect": "deny"},
    {"action": "subagent", "resource": "*", "effect": "deny"},
]


class OpenCodeServeBackend:
    """
    LLMBackend that delegates to opencode serve (API v2) via HTTP + SSE.

    Manages the opencode serve subprocess lifetime, creates/reuses sessions,
    translates the SSE event stream into ConversationBus events, and enforces
    PolicyEngine on every permission request emitted by OpenCode.

    Requires opencode >= 2.0: every route is under /api, HTTP basic auth is
    mandatory (password generated per process), and the working directory
    travels in the `x-opencode-directory` header instead of a query param.

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
        self._password: str = ""
        self._proc: subprocess.Popen | None = None
        self._session_id: str | None = None
        self._last_interaction: float = 0.0

        self._interrupted = threading.Event()
        # _sse_resp is set while query() is streaming; interrupt() closes it.
        self._sse_resp: object = None

        self._confirm_event = threading.Event()
        self._confirm_result: bool = True  # True=allow, False=deny

        # callIDs already published this session. Instance-scoped (not per turn)
        # so the REST sweep at the end of a turn cannot republish tools from
        # earlier turns. Cleared by reset_session().
        self._tool_called: set[str] = set()
        self._tool_resulted: set[str] = set()

        # Current context size in tokens. opencode serve does not deliver token
        # counts over the SSE stream, so this is refreshed from the REST API
        # (_fetch_session_tokens) after each turn. Zeroed on reset/compact.
        self._session_tokens: int = 0

    # ── subprocess lifecycle ─────────────────────────────────────────────

    def start(self) -> None:
        """Launch opencode serve and wait for it to print its URL on stdout.

        opencode 2.x requires HTTP basic auth on every route. We generate a
        per-process password and hand it over via OPENCODE_PASSWORD, which also
        suppresses the `server password` line the server would otherwise print.
        """
        args = [
            config.OPENCODE_BIN,
            "serve",
            f"--hostname={self._host}",
            f"--port={self._port}",
        ]
        if config.OPENCODE_SERVE_LOG:
            args.append("--print-logs")
        # Strip DBus so opencode cannot send its own desktop notifications for
        # permission requests — our harness handles those via the mobile/widget UI.
        self._password = secrets.token_urlsafe(32)
        env = {
            **os.environ,
            "DBUS_SESSION_BUS_ADDRESS": "",
            "OPENCODE_PASSWORD": self._password,
        }
        env.pop("OPENCODE_SERVER_PASSWORD", None)
        self._proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        deadline = time.time() + self._startup_timeout
        output_lines: list[str] = []
        while time.time() < deadline:
            line = self._proc.stdout.readline()  # type: ignore[union-attr]
            if not line:
                break
            output_lines.append(line.rstrip())
            m = re.search(r"server listening on\s+(https?://\S+)", line)
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

        # The system prompt goes into a session instruction entry so it survives
        # every turn. If that fails, fall back to prefixing the first message.
        prompt_text = text
        if new_session and system_prompt:
            blocks = [f"Follow these instructions for the ENTIRE conversation:\n\n{system_prompt}"]
            if obsidian_context:
                blocks.append(f"Restored context from your memory:\n\n{obsidian_context}")
            system_text = "\n\n---\n\n".join(blocks)
            if not (_USE_INSTRUCTION_ENTRIES and self._send_instructions(system_text)):
                prompt_text = f"{system_text}\n\n---\n\n{text}"

        # Open the SSE connection BEFORE sending the prompt so we never miss
        # events (including the terminal one) that arrive before the first read().
        # The v2 stream is GLOBAL — every event is filtered by sessionID below.
        sse_req = urllib.request.Request(
            f"{self._base_url}{_API}/event", headers=self._headers(sse=True)
        )

        # (assistantMessageID, ordinal) → accumulated text of that part.
        part_texts: dict[tuple[str, int], str] = {}
        # callID → tool name, learned from session.tool.input.started (the
        # name is not repeated on session.tool.called).
        tool_names: dict[str, str] = {}
        # Guards against a stale terminal event from a previous turn (e.g. an
        # `interrupted` that arrives after we already reopened the stream).
        turn_started = False
        error_msg = ""

        with urllib.request.urlopen(sse_req) as sse_resp:
            self._sse_resp = sse_resp
            try:
                # Prompt fires after SSE is open — no race condition.
                self._http_post(f"/session/{self._session_id}/prompt", {"text": prompt_text})

                for event in _parse_sse(sse_resp, self._interrupted):
                    etype = event.get("type") or ""
                    data = event.get("data") or {}

                    # form.created carries the form under data.form; the headless
                    # harness cancels it (the session rules deny `question`, but a
                    # plugin or MCP server could still open one).
                    if etype == "form.created":
                        self._cancel_form(data.get("form") or {})
                        continue

                    if data.get("sessionID") != self._session_id:
                        continue

                    if etype in ("session.execution.started", "session.step.started"):
                        turn_started = True

                    elif etype in ("session.text.delta", "session.text.ended"):
                        key = (data.get("assistantMessageID", ""), data.get("ordinal", 0))
                        if etype == "session.text.delta":
                            delta = data.get("delta", "")
                            part_texts[key] = part_texts.get(key, "") + delta
                            if delta:
                                self._bus.publish(TextDeltaEvent(delta=delta))
                        else:
                            # .ended carries the whole part; deltas are ephemeral.
                            part_texts[key] = data.get("text", part_texts.get(key, ""))

                    elif etype == "session.tool.input.started":
                        tool_names[data.get("id", "")] = data.get("name", "")

                    elif etype == "session.tool.called":
                        self._publish_tool_called(data, tool_names)

                    elif etype in ("session.tool.success", "session.tool.failed"):
                        self._publish_tool_result(etype, data, tool_names)

                    elif etype == "permission.asked":
                        self._handle_permission(data)

                    elif etype == "session.step.failed":
                        log.warning(
                            "opencode step failed: %s", (data.get("error") or {}).get("message", "")
                        )

                    elif etype in _TERMINAL_EVENTS:
                        if not turn_started:
                            log.debug("ignoring stale %s", etype)
                            continue
                        if etype == "session.execution.failed":
                            err = data.get("error") or {}
                            error_msg = (
                                err.get("message") if isinstance(err, dict) else str(err)
                            ) or "unknown error"
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

        # The REST message store is authoritative: it holds only the assistant's
        # "text" parts, with no reasoning mixed in. The streamed accumulation is
        # used only if the REST fetch itself fails (None) — an empty-but-
        # successful fetch means the model produced no answer text.
        final_text = self._fetch_final_text()
        full_text = final_text if final_text is not None else "".join(part_texts.values()).strip()
        if not full_text:
            log.warning("opencode serve: empty response")
            self._bus.publish(DoneEvent(content=i18n.t("no_response")))
            return LLMResult(i18n.t("no_response"), new_session, False, time.time() - t0)

        response = _strip_markdown(full_text)
        elapsed = time.time() - t0
        self._last_interaction = time.time()
        # Sweep the REST message store for any tool part the stream missed. The
        # instance-level dedup sets make this a no-op for tools already published
        # live, and keep earlier turns from being republished.
        self._publish_rest_tools()
        self._bus.publish(DoneEvent(content=response))
        log.info("opencode serve responded (%.2fs): %s", elapsed, response[:120])

        # Compact context if the session token budget is exceeded. opencode serve
        # does not emit token counts on the SSE stream, so read the authoritative
        # count from the REST API after the turn rather than accumulating events.
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
                # Verified in the 2.0.5 spike (S9): no request body; the server
                # answers 200 {"interrupted": true}.
                self._http_post(f"/session/{self._session_id}/interrupt")
            except Exception as exc:
                log.warning("opencode interrupt failed: %s", exc)
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
        self._tool_called.clear()
        self._tool_resulted.clear()
        log.info("opencode session reset")

    def _compact(self) -> None:
        """Trigger server-side context compaction via POST /api/session/{id}/compact.

        opencode 2.x also auto-compacts by default; this is the explicit trigger
        used when MIRACH_CONTEXT_STRATEGY=summarize and the budget is exceeded.
        Returns 200 with the resulting `type: "compaction"` message.
        """
        if not self._session_id or not self._base_url:
            return
        try:
            self._http_post(f"/session/{self._session_id}/compact", {})
        except Exception as exc:
            log.warning("opencode compact failed: %s", exc)
            return
        self._session_tokens = 0
        log.info("opencode context compacted (session %s)", self._session_id)

    def _fetch_last_assistant(self) -> dict | None:
        """The last assistant message of the current session, or None."""
        if not self._session_id or not self._base_url:
            return None
        result = self._http_get(
            f"/session/{self._session_id}/message",
            {"type": "assistant", "order": "desc", "limit": "1"},
        )
        messages = result.get("data") or []
        return messages[0] if messages else None

    def _fetch_session_tokens(self) -> int:
        """Current context size in tokens = the last assistant message's
        input+output, read from GET /api/session/{id}/message.

        The last assistant message's `input` already reflects the full prompt
        (system + history), so `input + output` approximates the context
        footprint. Returns the previous value on failure so a transient error
        can't silently wipe the budget and trigger a needless compact.
        """
        try:
            msg = self._fetch_last_assistant()
        except Exception as exc:
            log.warning("could not fetch session tokens: %s", exc)
            return self._session_tokens
        if msg is None:
            return 0
        tk = msg.get("tokens") or {}
        return tk.get("input", 0) + tk.get("output", 0)

    def _fetch_final_text(self) -> str | None:
        """Authoritative answer text for the turn that just finished.

        Concatenates only the `"text"` parts of the last assistant message —
        reasoning is a separate event stream in v2 and never lands here.
        Returns None on fetch failure (caller may fall back to streamed text);
        returns "" when the fetch succeeded but the model produced no answer.
        """
        try:
            msg = self._fetch_last_assistant()
        except Exception as exc:
            log.warning("could not fetch final message: %s", exc)
            return None
        if msg is None:
            return None
        return "".join(
            p.get("text", "")
            for p in msg.get("content") or []
            if isinstance(p, dict) and p.get("type") == "text"
        ).strip()

    def reply_confirmation(self, allow: bool) -> None:
        """Signal a pending CONFIRM permission request from external code."""
        self._confirm_result = allow
        self._confirm_event.set()

    # ── tool events → bus ────────────────────────────────────────────────

    def _publish_tool_called(self, data: dict, names: dict[str, str]) -> None:
        """Publish a ToolCallEvent for a `session.tool.called` event."""
        call_id = data.get("id", "")
        if call_id in self._tool_called:
            return
        self._tool_called.add(call_id)
        self._bus.publish(
            ToolCallEvent(
                id=call_id,
                name=names.get(call_id, ""),
                arguments=data.get("input") or {},
            )
        )

    def _publish_tool_result(self, etype: str, data: dict, names: dict[str, str]) -> None:
        """Publish a ToolResultEvent for `session.tool.success` / `.failed`."""
        call_id = data.get("id", "")
        if call_id not in self._tool_called:
            # A result without its call (missed event) still needs the pair.
            self._tool_called.add(call_id)
            self._bus.publish(ToolCallEvent(id=call_id, name=names.get(call_id, ""), arguments={}))
        if call_id in self._tool_resulted:
            return
        self._tool_resulted.add(call_id)
        failed = etype.endswith("failed")
        result = (
            (data.get("error") or {}).get("message", "")
            if failed
            else _content_text(data.get("content"))
        )
        self._bus.publish(
            ToolResultEvent(
                tool_call_id=call_id,
                result=str(result or "")[:2000],
                error=failed,
            )
        )

    def _publish_rest_tools(self) -> None:
        """Publish any tool part the SSE stream did not deliver.

        Walks the recent assistant messages of the session and feeds every
        `type == "tool"` part through _publish_tool_part. The instance-level
        dedup sets make it idempotent and keep earlier turns out.
        """
        if not self._session_id or not self._base_url:
            return
        try:
            result = self._http_get(
                f"/session/{self._session_id}/message",
                {"type": "assistant", "order": "desc", "limit": "20"},
            )
        except Exception as exc:
            log.warning("could not fetch tool parts: %s", exc)
            return
        for msg in reversed(result.get("data") or []):
            for part in msg.get("content") or []:
                if isinstance(part, dict) and part.get("type") == "tool":
                    self._publish_tool_part(part)

    def _publish_tool_part(self, part: dict) -> None:
        """Translate a REST tool part into tool_call/tool_result events."""
        call_id = part.get("id", "")
        state = part.get("state") or {}
        status = state.get("status", "")

        if call_id not in self._tool_called and status in ("running", "completed", "error"):
            self._tool_called.add(call_id)
            inputs = state.get("input")
            self._bus.publish(
                ToolCallEvent(
                    id=call_id,
                    name=part.get("name", ""),
                    arguments=inputs if isinstance(inputs, dict) else {},
                )
            )
        if call_id not in self._tool_resulted and status in ("completed", "error"):
            self._tool_resulted.add(call_id)
            output = _content_text(state.get("content")) or (state.get("error") or {}).get(
                "message", ""
            )
            self._bus.publish(
                ToolResultEvent(
                    tool_call_id=call_id,
                    result=str(output or "")[:2000],
                    error=status == "error",
                )
            )

    # ── permission handling ──────────────────────────────────────────────

    def _handle_permission(self, data: dict) -> None:
        """Decide an opencode permission request against the harness policy.

        v2 `permission.asked` payload:
        {id, sessionID, action, resources: [...], save?, metadata?,
         source?: {type, messageID, id}, message?}

        `resources` can hold several targets; the strictest policy decision
        across all of them wins.
        """
        perm_id = data.get("id", "")
        session_id = data.get("sessionID") or self._session_id or ""
        action = data.get("action", "")
        resources = [r for r in (data.get("resources") or []) if isinstance(r, str)]
        metadata = data.get("metadata") or {}
        call_id = (data.get("source") or {}).get("id", "")
        title = data.get("message") or action
        pattern = "; ".join(resources)

        tool = _opencode_type_to_policy_tool(action)
        decision = _strictest(
            [self._policy.check(tool, _policy_args(action, r)) for r in (resources or [""])]
        )

        if decision == Decision.ALLOW:
            self._reply_permission(session_id, perm_id, "once")

        elif decision == Decision.DENY:
            # Make the policy denial visible to clients — otherwise the tool
            # silently fails and the user can't tell why nothing happened.
            self._bus.publish(ErrorEvent(message=f"[policy] {action} denied: {pattern or title}"))
            self._reply_permission(session_id, perm_id, "reject")

        else:  # CONFIRM
            confirm_args: dict = {"title": title}
            if pattern:
                confirm_args["pattern"] = pattern
            confirm_args.update(metadata)
            self._bus.publish(
                AwaitingConfirmationEvent(
                    tool_call_id=call_id or perm_id,
                    # Keep the v1 name on the wire so the mobile/voice clients
                    # do not have to learn opencode's new action vocabulary.
                    name="bash" if action == "shell" else action,
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
                f"/session/{session_id}/permission/{perm_id}/reply",
                {"decision": response},
            )
            log.info("Permission %s → %s", perm_id, response)
        except Exception as exc:
            log.warning("Permission reply failed: %s", exc)

    def _cancel_form(self, form: dict) -> None:
        """Dismiss an interactive form — this harness is headless."""
        if form.get("sessionID") != self._session_id:
            return
        try:
            self._http_delete(f"/session/{self._session_id}/form/{form.get('id', '')}")
            log.warning("cancelled opencode form %s (headless)", form.get("id", ""))
        except Exception as exc:
            log.warning("could not cancel opencode form: %s", exc)

    # ── HTTP helpers ─────────────────────────────────────────────────────

    def _headers(self, *, json_body: bool = False, sse: bool = False) -> dict[str, str]:
        """Auth + working directory, required on every opencode 2.x request."""
        token = base64.b64encode(f"opencode:{self._password}".encode()).decode()
        h = {"Authorization": f"Basic {token}", "x-opencode-directory": quote(self._cwd)}
        if json_body:
            h["Content-Type"] = "application/json"
        if sse:
            h["Accept"] = "text/event-stream"
        return h

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        params: dict | None = None,
        timeout: float = 30.0,
    ) -> dict:
        url = f"{self._base_url}{_API}{path}"
        if params:
            url += "?" + urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        if data is None and method in ("POST", "PUT"):
            data = b""
        req = urllib.request.Request(
            url,
            data=data,
            headers=self._headers(json_body=body is not None),
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise RuntimeError(_http_error_text(exc)) from exc

    def _http_post(self, path: str, body: dict | None = None) -> dict:
        return self._request("POST", path, body, timeout=30.0)

    def _http_put(self, path: str, body: dict) -> dict:
        return self._request("PUT", path, body, timeout=30.0)

    def _http_get(self, path: str, params: dict | None = None) -> dict:
        return self._request("GET", path, None, params, timeout=15.0)

    def _http_delete(self, path: str) -> None:
        self._request("DELETE", path, None, timeout=10.0)

    def _create_session(self) -> str:
        """Create a session that carries our permission rules and model.

        The rules travel with the session because opencode.json is resolved from
        the cwd, which in production is the daemon's ($HOME) — not the repo.
        """
        body: dict = {"permissions": _SESSION_RULES, "location": {"directory": self._cwd}}
        if self._provider_id and self._model_id:
            body["model"] = {"providerID": self._provider_id, "id": self._model_id}
        try:
            result = self._http_post("/session", body)
        except RuntimeError as exc:
            if "HTTP 404" in str(exc):
                raise RuntimeError(
                    "opencode serve does not expose the v2 API (/api/session → 404). "
                    "Mirach requires opencode >= 2.0"
                ) from exc
            raise
        return result["data"]["id"]

    def _send_instructions(self, text: str) -> bool:
        """Store the system prompt as a session instruction entry.

        Returns False if the server rejected it, so the caller can fall back to
        prefixing the text onto the first user message.
        """
        try:
            self._http_put(
                f"/experimental/session/{self._session_id}/instructions/entries/{_INSTRUCTION_KEY}",
                {"value": text},
            )
        except Exception as exc:
            log.warning("could not set opencode instructions: %s", exc)
            return False
        return True


# ── module-level helpers ──────────────────────────────────────────────────────


def _http_error_text(exc: urllib.error.HTTPError) -> str:
    """Readable message for an opencode 2.x error.

    Errors are flat objects — {_tag, message, ...} — with no `data` envelope.
    """
    try:
        raw = exc.read().decode("utf-8", "replace")
    except Exception:
        raw = ""
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        payload = None
    if isinstance(payload, dict):
        tag = payload.get("_tag", "")
        message = payload.get("message", "")
        return f"opencode HTTP {exc.code} {tag}: {message}"
    return f"opencode HTTP {exc.code}: {raw[:300]}"


def _content_text(content: object) -> str:
    """Concatenate the `text` blocks of a tool result's content array."""
    if not isinstance(content, list):
        return ""
    return "".join(
        c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"
    )


def _policy_args(action: str, resource: str) -> dict:
    """Build PolicyEngine args from one opencode permission resource."""
    if action in ("shell", "bash"):
        return {"command": resource}
    if action in ("edit", "read", "external_directory"):
        return {"path": resource[:-2] if resource.endswith("/*") else resource}
    if action == "webfetch":
        return {"url": resource}
    return {}


def _strictest(decisions: list[Decision]) -> Decision:
    """The most restrictive decision of the lot: DENY > CONFIRM > ALLOW."""
    if Decision.DENY in decisions:
        return Decision.DENY
    if Decision.CONFIRM in decisions:
        return Decision.CONFIRM
    return Decision.ALLOW


def _opencode_type_to_policy_tool(opencode_type: str) -> str:
    """Map an opencode permission action → PolicyEngine tool name."""
    return {
        "shell": "bash",
        "bash": "bash",
        "edit": "edit_file",
        "webfetch": "web_fetch",
        "websearch": "web_search",
        "external_directory": "read_file",
        "read": "read_file",
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
