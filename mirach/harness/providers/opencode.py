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
    CostEvent,
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from mirach.harness.policy.engine import Decision, PolicyEngine
from mirach.llm_types import LLMResult, _strip_markdown
from mirach.logging_setup import log

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

    # ── subprocess lifecycle ─────────────────────────────────────────────

    def start(self) -> None:
        """Launch opencode serve and wait for it to print its URL on stdout."""
        args = [
            "opencode",
            "serve",
            f"--hostname={self._host}",
            f"--port={self._port}",
        ]
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
                    return
        raise RuntimeError(
            f"opencode serve did not start within {self._startup_timeout}s. Output: {output_lines}"
        )

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

        self._http_post(f"/session/{self._session_id}/prompt_async", body)

        # Stream events; accumulate final text via part_id → full_text_so_far
        part_texts: dict[str, str] = {}
        error_msg = ""

        try:
            for event in self._iter_events():
                etype = event.get("type")
                props = event.get("properties", {})

                if etype == "message.part.updated":
                    part = props.get("part", {})
                    delta = props.get("delta")
                    self._handle_part(part, delta, part_texts)

                elif etype == "message.updated":
                    info = props.get("info", {})
                    if info.get("role") == "assistant":
                        tokens = info.get("tokens", {})
                        self._bus.publish(
                            CostEvent(
                                input_tokens=tokens.get("input", 0),
                                output_tokens=tokens.get("output", 0),
                            )
                        )

                elif etype == "permission.updated":
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

        if self._interrupted.is_set():
            return LLMResult("", new_session, True, time.time() - t0)

        if error_msg:
            self._bus.publish(ErrorEvent(message=error_msg))
            return LLMResult(i18n.t("generic_error"), new_session, False, time.time() - t0)

        full_text = "".join(part_texts.values()).strip()
        if not full_text:
            log.warning("opencode serve: empty response")
            return LLMResult(i18n.t("no_response"), new_session, False, time.time() - t0)

        response = _strip_markdown(full_text)
        elapsed = time.time() - t0
        self._last_interaction = time.time()
        self._bus.publish(DoneEvent(content=response))
        log.info("opencode serve responded (%.2fs): %s", elapsed, response[:120])
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
        log.info("opencode session reset")

    def reply_confirmation(self, allow: bool) -> None:
        """Signal a pending CONFIRM permission request from external code."""
        self._confirm_result = allow
        self._confirm_event.set()

    # ── permission handling ──────────────────────────────────────────────

    def _handle_permission(self, props: dict) -> None:
        perm_id = props.get("id", "")
        session_id = props.get("sessionID") or self._session_id or ""
        tool_type = props.get("type", "")
        pattern = props.get("pattern")
        title = props.get("title", tool_type)
        metadata = props.get("metadata", {}) or {}
        call_id = props.get("callID", "")

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

    # ── event part translation ───────────────────────────────────────────

    def _handle_part(self, part: dict, delta: str | None, part_texts: dict[str, str]) -> None:
        ptype = part.get("type")

        if ptype == "text" and not part.get("synthetic"):
            part_texts[part.get("id", "")] = part.get("text", "")
            if delta:
                self._bus.publish(TextDeltaEvent(delta=delta))

        elif ptype == "tool":
            state = part.get("state", {})
            status = state.get("status")
            tool_name = part.get("tool", "")
            call_id = part.get("callID", part.get("id", ""))

            if status == "pending":
                self._bus.publish(
                    ToolCallEvent(
                        id=call_id,
                        name=tool_name,
                        arguments=state.get("input", {}),
                    )
                )

            elif status in ("completed", "error"):
                output = (
                    state.get("output", "") if status == "completed" else state.get("error", "")
                )
                self._bus.publish(
                    ToolResultEvent(
                        tool_call_id=call_id,
                        result=str(output),
                        error=(status == "error"),
                    )
                )

    # ── SSE streaming ────────────────────────────────────────────────────

    def _iter_events(self) -> Iterator[dict]:
        """Open GET /event and yield parsed event dicts until the stream closes."""
        params = urlencode({"directory": self._cwd})
        url = f"{self._base_url}/event?{params}"
        req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
        with urllib.request.urlopen(req) as resp:  # type: ignore[arg-type]
            self._sse_resp = resp
            try:
                yield from _parse_sse(resp, self._interrupted)
            finally:
                self._sse_resp = None

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
    buf = b""
    try:
        while not interrupted.is_set():
            try:
                chunk = response.read(4096)  # type: ignore[union-attr]
            except Exception:
                break
            if not chunk:
                break
            buf += chunk
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
