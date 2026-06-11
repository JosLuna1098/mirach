"""Tests for OpenCodeServeBackend — mocked SSE stream, no real opencode server."""

from __future__ import annotations

import io
import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from mirach.harness.events import (
    AwaitingConfirmationEvent,
    ConversationBus,
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
)
from mirach.harness.policy.engine import Decision, PolicyEngine
from mirach.harness.providers.opencode import (
    OpenCodeServeBackend,
    _opencode_type_to_policy_tool,
    _parse_sse,
)


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_sse_bytes(*events: dict) -> bytes:
    """Encode a sequence of dicts as SSE data frames."""
    out = b""
    for ev in events:
        out += b"data: " + json.dumps(ev).encode() + b"\n\n"
    return out


def _text_delta(part_id: str, delta: str, session_id: str = "sess-1") -> dict:
    """Build a message.part.delta event for text streaming (real API format)."""
    return {
        "type": "message.part.delta",
        "properties": {
            "sessionID": session_id,
            "partID": part_id,
            "field": "text",
            "delta": delta,
        },
    }


def _session_idle(session_id: str = "sess-1") -> dict:
    return {"type": "session.idle", "properties": {"sessionID": session_id}}


class _FakeResp:
    """Minimal urllib response mock supporting read() and context-manager protocol."""

    def __init__(self, body: bytes) -> None:
        self._buf = io.BytesIO(body)
        self.closed = False

    def read(self, n: int = -1) -> bytes:
        if self.closed:
            raise OSError("closed")
        return self._buf.read(n)

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class _BlockingFakeResp(_FakeResp):
    """SSE response that yields initial_data then blocks on read() until close()."""

    def __init__(self, initial_data: bytes) -> None:
        super().__init__(initial_data)
        self._gate = threading.Event()

    def read(self, n: int = -1) -> bytes:
        data = self._buf.read(n)
        if data:
            return data
        # Block until close() is called
        self._gate.wait()
        raise OSError("closed")

    def close(self) -> None:
        self.closed = True
        self._gate.set()


def _make_backend(
    *,
    policy: PolicyEngine | None = None,
    bus: ConversationBus | None = None,
) -> OpenCodeServeBackend:
    """Return a backend with a pre-set URL and session (no subprocess)."""
    backend = OpenCodeServeBackend(
        policy=policy or PolicyEngine(),
        bus=bus or ConversationBus(),
        cwd="/tmp/test",
    )
    backend._base_url = "http://localhost:9999"
    backend._session_id = "sess-1"
    backend._last_interaction = time.time()  # prevent session_expired on first call
    return backend


def _mock_urlopen(sse_events: list[dict], rest_responses: dict[str, object] | None = None):
    """
    Build a side_effect function for urllib.request.urlopen.

    GET /event → FakeResp with SSE bytes.
    Everything else → FakeResp with JSON from rest_responses[path] or {}.
    """
    rest = rest_responses or {}

    def _side_effect(req_or_url, timeout=None):
        url = req_or_url if isinstance(req_or_url, str) else req_or_url.full_url
        if "/event" in url:
            return _FakeResp(_make_sse_bytes(*sse_events))
        for key, payload in rest.items():
            if key in url:
                body = json.dumps(payload).encode() if payload else b""
                return _FakeResp(body)
        return _FakeResp(b"{}")

    return _side_effect


# ── _parse_sse unit tests ─────────────────────────────────────────────────────


def test_parse_sse_basic():
    ev = {"type": "session.idle", "properties": {"sessionID": "x"}}
    resp = _FakeResp(_make_sse_bytes(ev))
    result = list(_parse_sse(resp, threading.Event()))
    assert result == [ev]


def test_parse_sse_multiple_events():
    events = [
        _text_delta("p1", "Hi"),
        _session_idle(),
    ]
    resp = _FakeResp(_make_sse_bytes(*events))
    result = list(_parse_sse(resp, threading.Event()))
    assert result == events


def test_parse_sse_stops_on_interrupt():
    interrupted = threading.Event()
    interrupted.set()
    events = [_session_idle()]
    resp = _FakeResp(_make_sse_bytes(*events))
    result = list(_parse_sse(resp, interrupted))
    assert result == []


def test_parse_sse_ignores_malformed_json():
    raw = b"data: not-json\n\ndata: {\"type\": \"ok\"}\n\n"
    resp = _FakeResp(raw)
    result = list(_parse_sse(resp, threading.Event()))
    assert result == [{"type": "ok"}]


def test_parse_sse_handles_crlf_line_endings():
    ev = {"type": "session.idle", "properties": {"sessionID": "x"}}
    crlf_bytes = b"data: " + json.dumps(ev).encode() + b"\r\n\r\n"
    resp = _FakeResp(crlf_bytes)
    result = list(_parse_sse(resp, threading.Event()))
    assert result == [ev]


# ── _opencode_type_to_policy_tool ─────────────────────────────────────────────


@pytest.mark.parametrize("oc_type,expected", [
    ("bash", "bash"),
    ("edit", "edit_file"),
    ("webfetch", "web_fetch"),
    ("doom_loop", "bash"),
    ("external_directory", "read_file"),
    ("unknown_tool", "unknown_tool"),
])
def test_type_mapping(oc_type, expected):
    assert _opencode_type_to_policy_tool(oc_type) == expected


# ── query: text streaming ─────────────────────────────────────────────────────


def test_query_text_streaming():
    """Text deltas are emitted as TextDeltaEvents; final text is returned in LLMResult."""
    bus = ConversationBus()
    received: list[object] = []
    bus.subscribe(received.append)

    backend = _make_backend(bus=bus)
    sse = [
        _text_delta("p1", "Hello"),
        _text_delta("p1", " world"),
        _session_idle(),
    ]

    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse)):
        result = backend.query("hi", "")

    assert result.response == "Hello world"
    assert not result.interrupted
    text_deltas = [e for e in received if isinstance(e, TextDeltaEvent)]
    assert [e.delta for e in text_deltas] == ["Hello", " world"]
    assert any(isinstance(e, DoneEvent) for e in received)


def test_query_non_text_fields_are_ignored():
    """Deltas with field != 'text' (e.g. tool input streaming) must not affect response."""
    bus = ConversationBus()
    received: list[object] = []
    bus.subscribe(received.append)

    backend = _make_backend(bus=bus)
    sse = [
        # Tool input delta — should be ignored for text accumulation
        {"type": "message.part.delta", "properties": {
            "sessionID": "sess-1", "partID": "t1", "field": "input", "delta": '{"cmd":',
        }},
        _text_delta("p1", "Done"),
        _session_idle(),
    ]

    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse)):
        result = backend.query("hi", "")

    assert result.response == "Done"
    text_deltas = [e for e in received if isinstance(e, TextDeltaEvent)]
    assert [e.delta for e in text_deltas] == ["Done"]


def test_query_multiple_parts_concatenated():
    """Deltas from different partIDs are concatenated in order."""
    backend = _make_backend()
    sse = [
        _text_delta("p1", "foo"),
        _text_delta("p2", "bar"),
        _session_idle(),
    ]
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse)):
        result = backend.query("hi", "")
    # part_texts = {"p1": "foo", "p2": "bar"} → joined: "foobar"
    assert result.response == "foobar"


# ── query: session error ──────────────────────────────────────────────────────


def test_query_session_error():
    bus = ConversationBus()
    received: list[object] = []
    bus.subscribe(received.append)

    backend = _make_backend(bus=bus)
    sse = [
        {"type": "session.error", "properties": {
            "sessionID": "sess-1",
            "error": {"name": "UnknownError", "data": {"message": "boom"}},
        }},
    ]

    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse)):
        result = backend.query("hi", "")

    errors = [e for e in received if isinstance(e, ErrorEvent)]
    assert len(errors) == 1
    assert "boom" in errors[0].message
    assert not result.interrupted


# ── permission: ALLOW ─────────────────────────────────────────────────────────


def test_permission_allow():
    """PolicyEngine ALLOW → POST "once" immediately."""
    policy = MagicMock(spec=PolicyEngine)
    policy.check.return_value = Decision.ALLOW

    bus = ConversationBus()
    backend = _make_backend(policy=policy, bus=bus)

    perm_event = {
        "type": "permission.updated",
        "properties": {
            "id": "perm-1", "sessionID": "sess-1",
            "type": "bash", "pattern": "ls", "title": "Run ls",
            "callID": "c1", "metadata": {}, "time": {"created": 0},
        },
    }
    sse = [
        perm_event,
        _text_delta("p1", "ok"),
        _session_idle(),
    ]

    posted: list[tuple[str, dict]] = []

    def _urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if "/event" in url:
            return _FakeResp(_make_sse_bytes(*sse))
        if hasattr(req, "data") and req.data:
            posted.append((url, json.loads(req.data)))
        return _FakeResp(b"{}")

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        backend.query("hi", "")

    policy.check.assert_called_once_with("bash", {"command": "ls"})
    perm_replies = [(u, b) for u, b in posted if "permissions" in u]
    assert len(perm_replies) == 1
    assert perm_replies[0][1] == {"response": "once"}


# ── permission: DENY ──────────────────────────────────────────────────────────


def test_permission_deny():
    """PolicyEngine DENY → POST "reject"."""
    policy = MagicMock(spec=PolicyEngine)
    policy.check.return_value = Decision.DENY

    backend = _make_backend(policy=policy)
    perm_event = {
        "type": "permission.updated",
        "properties": {
            "id": "perm-2", "sessionID": "sess-1",
            "type": "bash", "pattern": "rm -rf /", "title": "Delete root",
            "callID": "c2", "metadata": {}, "time": {"created": 0},
        },
    }
    sse = [
        perm_event,
        _text_delta("p1", "denied"),
        _session_idle(),
    ]

    posted: list[tuple[str, dict]] = []

    def _urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if "/event" in url:
            return _FakeResp(_make_sse_bytes(*sse))
        if hasattr(req, "data") and req.data:
            posted.append((url, json.loads(req.data)))
        return _FakeResp(b"{}")

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        backend.query("delete everything", "")

    perm_replies = [(u, b) for u, b in posted if "permissions" in u]
    assert perm_replies[0][1] == {"response": "reject"}


# ── permission: CONFIRM → allow ───────────────────────────────────────────────


def test_permission_confirm_user_allows():
    """CONFIRM path: AwaitingConfirmationEvent emitted, user allows → POST "once"."""
    policy = MagicMock(spec=PolicyEngine)
    policy.check.return_value = Decision.CONFIRM

    bus = ConversationBus()
    received: list[object] = []
    bus.subscribe(received.append)

    backend = _make_backend(policy=policy, bus=bus)

    perm_event = {
        "type": "permission.updated",
        "properties": {
            "id": "perm-3", "sessionID": "sess-1",
            "type": "bash", "pattern": "git push", "title": "Push",
            "callID": "c3", "metadata": {}, "time": {"created": 0},
        },
    }
    sse = [
        perm_event,
        _text_delta("p1", "pushed"),
        _session_idle(),
    ]

    posted: list[tuple[str, dict]] = []

    def _urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if "/event" in url:
            return _FakeResp(_make_sse_bytes(*sse))
        if hasattr(req, "data") and req.data:
            posted.append((url, json.loads(req.data)))
        return _FakeResp(b"{}")

    def _allow_after_delay():
        time.sleep(0.05)
        backend.reply_confirmation(allow=True)

    threading.Thread(target=_allow_after_delay, daemon=True).start()

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        backend.query("git push", "")

    confirms = [e for e in received if isinstance(e, AwaitingConfirmationEvent)]
    assert len(confirms) == 1
    assert confirms[0].name == "bash"

    perm_replies = [(u, b) for u, b in posted if "permissions" in u]
    assert perm_replies[0][1] == {"response": "once"}


# ── permission: CONFIRM → deny ────────────────────────────────────────────────


def test_permission_confirm_user_denies():
    """CONFIRM path: user denies → POST "reject"."""
    policy = MagicMock(spec=PolicyEngine)
    policy.check.return_value = Decision.CONFIRM

    backend = _make_backend(policy=policy)

    perm_event = {
        "type": "permission.updated",
        "properties": {
            "id": "perm-4", "sessionID": "sess-1",
            "type": "bash", "pattern": "git push", "title": "Push",
            "callID": "c4", "metadata": {}, "time": {"created": 0},
        },
    }
    sse = [
        perm_event,
        _text_delta("p1", "not pushed"),
        _session_idle(),
    ]

    posted: list[tuple[str, dict]] = []

    def _urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if "/event" in url:
            return _FakeResp(_make_sse_bytes(*sse))
        if hasattr(req, "data") and req.data:
            posted.append((url, json.loads(req.data)))
        return _FakeResp(b"{}")

    def _deny_after_delay():
        time.sleep(0.05)
        backend.reply_confirmation(allow=False)

    threading.Thread(target=_deny_after_delay, daemon=True).start()

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        backend.query("git push", "")

    perm_replies = [(u, b) for u, b in posted if "permissions" in u]
    assert perm_replies[0][1] == {"response": "reject"}


# ── permission: CONFIRM timeout → reject ──────────────────────────────────────


def test_permission_confirm_timeout():
    """CONFIRM path: timeout → POST "reject"."""
    import mirach.harness.providers.opencode as oc_module

    policy = MagicMock(spec=PolicyEngine)
    policy.check.return_value = Decision.CONFIRM

    backend = _make_backend(policy=policy)

    perm_event = {
        "type": "permission.updated",
        "properties": {
            "id": "perm-5", "sessionID": "sess-1",
            "type": "bash", "pattern": "git push", "title": "Push",
            "callID": "c5", "metadata": {}, "time": {"created": 0},
        },
    }
    sse = [
        perm_event,
        _text_delta("p1", "nope"),
        _session_idle(),
    ]

    posted: list[tuple[str, dict]] = []

    def _urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if "/event" in url:
            return _FakeResp(_make_sse_bytes(*sse))
        if hasattr(req, "data") and req.data:
            posted.append((url, json.loads(req.data)))
        return _FakeResp(b"{}")

    with patch.object(oc_module, "_CONFIRM_TIMEOUT", 0.05):
        with patch("urllib.request.urlopen", side_effect=_urlopen):
            backend.query("git push", "")

    perm_replies = [(u, b) for u, b in posted if "permissions" in u]
    assert perm_replies[0][1] == {"response": "reject"}


# ── interrupt ─────────────────────────────────────────────────────────────────


def test_interrupt_returns_interrupted_result():
    """interrupt() while streaming blocks → LLMResult with interrupted=True."""
    backend = _make_backend()

    initial_sse = _make_sse_bytes(_text_delta("p1", "..."))

    blocking_resp: list[_BlockingFakeResp] = []

    def _urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if "/event" in url:
            resp = _BlockingFakeResp(initial_sse)
            blocking_resp.append(resp)
            return resp
        return _FakeResp(b"{}")

    def _interrupt():
        time.sleep(0.03)
        backend.interrupt()

    threading.Thread(target=_interrupt, daemon=True).start()

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        result = backend.query("hi", "")

    assert result.interrupted is True
    assert result.response == ""


# ── session management ────────────────────────────────────────────────────────


def test_session_expired_on_first_use():
    backend = OpenCodeServeBackend(
        policy=PolicyEngine(),
        bus=ConversationBus(),
        cwd="/tmp",
    )
    backend._base_url = "http://localhost:9999"
    assert backend.session_expired()


def test_session_not_expired_after_interaction():
    backend = _make_backend()
    assert not backend.session_expired()


def test_session_expired_after_timeout(monkeypatch):
    backend = _make_backend()
    monkeypatch.setattr("mirach.config.SESSION_IDLE_TIMEOUT", 0.0)
    assert backend.session_expired()


def test_reset_session_calls_delete():
    posted_deletes: list[str] = []

    def _urlopen(req, timeout=None):
        if hasattr(req, "method") and req.method == "DELETE":
            posted_deletes.append(req.full_url)
        return _FakeResp(b"true")

    backend = _make_backend()
    with patch("urllib.request.urlopen", side_effect=_urlopen):
        backend.reset_session()

    assert backend._session_id is None
    assert any("sess-1" in u for u in posted_deletes)


def test_reset_session_skips_delete_when_no_session():
    backend = _make_backend()
    backend._session_id = None

    called = []

    def _urlopen(req, timeout=None):
        called.append(req)
        return _FakeResp(b"{}")

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        backend.reset_session()

    assert not called


def test_query_creates_session_when_none():
    """First query with no session_id → POST /session to create one."""
    backend = OpenCodeServeBackend(
        policy=PolicyEngine(),
        bus=ConversationBus(),
        cwd="/tmp",
    )
    backend._base_url = "http://localhost:9999"

    sse = [
        _text_delta("p1", "hello", session_id="new-sess"),
        _session_idle("new-sess"),
    ]

    def _urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if "/event" in url:
            return _FakeResp(_make_sse_bytes(*sse))
        if "/session" in url and not any(
            x in url for x in ["prompt_async", "permissions", "abort"]
        ):
            method = getattr(req, "method", "GET")
            if method == "POST" and req.data == b"{}":
                return _FakeResp(json.dumps({"id": "new-sess"}).encode())
        return _FakeResp(b"{}")

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        result = backend.query("hi", "")

    assert backend._session_id == "new-sess"
    assert result.response == "hello"


# ── new session: system prompt injection ─────────────────────────────────────


def test_query_injects_system_prompt_on_new_session():
    """On a new session, system_prompt is included in the POST body."""
    backend = _make_backend()
    backend._last_interaction = 0.0  # force new session
    backend._session_id = "sess-1"

    sse = [
        _text_delta("p1", "ok"),
        _session_idle(),
    ]

    bodies: list[dict] = []

    def _urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if "/event" in url:
            return _FakeResp(_make_sse_bytes(*sse))
        if hasattr(req, "data") and req.data:
            try:
                bodies.append(json.loads(req.data))
            except Exception:
                pass
        if "/session" in url and not any(
            x in url for x in ["prompt_async", "permissions", "abort"]
        ):
            method = getattr(req, "method", "POST")
            if method == "POST":
                return _FakeResp(json.dumps({"id": "sess-1"}).encode())
        return _FakeResp(b"{}")

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        backend.query("hi", system_prompt="Be helpful.", obsidian_context="")

    prompt_bodies = [b for b in bodies if "parts" in b]
    assert len(prompt_bodies) == 1
    assert "system" in prompt_bodies[0]
    assert "Be helpful." in prompt_bodies[0]["system"]


def test_query_no_system_prompt_on_existing_session():
    """On a non-new session, system prompt is NOT re-injected."""
    backend = _make_backend()

    sse = [
        _text_delta("p1", "ok"),
        _session_idle(),
    ]

    bodies: list[dict] = []

    def _urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if "/event" in url:
            return _FakeResp(_make_sse_bytes(*sse))
        if hasattr(req, "data") and req.data:
            try:
                bodies.append(json.loads(req.data))
            except Exception:
                pass
        return _FakeResp(b"{}")

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        backend.query("hi", system_prompt="Be helpful.")

    prompt_bodies = [b for b in bodies if "parts" in b]
    assert "system" not in prompt_bodies[0]
