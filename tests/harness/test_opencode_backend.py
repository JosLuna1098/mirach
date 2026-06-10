"""Tests for OpenCodeServeBackend — mocked SSE stream, no real opencode server."""

from __future__ import annotations

import io
import json
import threading
import time
from unittest.mock import MagicMock, call, patch

import pytest

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
        # Match first rest key found in the URL
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
        {"type": "message.part.updated", "properties": {"part": {"type": "text", "id": "p1", "text": "Hi"}, "delta": "Hi"}},
        {"type": "session.idle", "properties": {"sessionID": "s"}},
    ]
    resp = _FakeResp(_make_sse_bytes(*events))
    result = list(_parse_sse(resp, threading.Event()))
    assert result == events


def test_parse_sse_stops_on_interrupt():
    interrupted = threading.Event()
    interrupted.set()
    events = [{"type": "session.idle", "properties": {}}]
    resp = _FakeResp(_make_sse_bytes(*events))
    result = list(_parse_sse(resp, interrupted))
    assert result == []


def test_parse_sse_ignores_malformed_json():
    raw = b"data: not-json\n\ndata: {\"type\": \"ok\"}\n\n"
    resp = _FakeResp(raw)
    result = list(_parse_sse(resp, threading.Event()))
    assert result == [{"type": "ok"}]


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
        {"type": "message.part.updated", "properties": {
            "part": {"type": "text", "id": "p1", "text": "Hello", "synthetic": False},
            "delta": "Hello",
        }},
        {"type": "message.part.updated", "properties": {
            "part": {"type": "text", "id": "p1", "text": "Hello world", "synthetic": False},
            "delta": " world",
        }},
        {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
    ]

    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse)):
        result = backend.query("hi", "")

    assert result.response == "Hello world"
    assert not result.interrupted
    text_deltas = [e for e in received if isinstance(e, TextDeltaEvent)]
    assert [e.delta for e in text_deltas] == ["Hello", " world"]
    assert any(isinstance(e, DoneEvent) for e in received)


def test_query_ignores_synthetic_parts():
    bus = ConversationBus()
    received: list[object] = []
    bus.subscribe(received.append)

    backend = _make_backend(bus=bus)
    sse = [
        {"type": "message.part.updated", "properties": {
            "part": {"type": "text", "id": "p0", "text": "synthetic", "synthetic": True},
            "delta": "synthetic",
        }},
        {"type": "message.part.updated", "properties": {
            "part": {"type": "text", "id": "p1", "text": "real", "synthetic": False},
            "delta": "real",
        }},
        {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
    ]

    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse)):
        result = backend.query("hi", "")

    assert result.response == "real"
    text_deltas = [e for e in received if isinstance(e, TextDeltaEvent)]
    assert [e.delta for e in text_deltas] == ["real"]


# ── query: tool events ────────────────────────────────────────────────────────


def test_query_tool_events():
    bus = ConversationBus()
    received: list[object] = []
    bus.subscribe(received.append)

    backend = _make_backend(bus=bus)
    sse = [
        {"type": "message.part.updated", "properties": {
            "part": {"type": "tool", "id": "t1", "callID": "c1", "tool": "bash",
                     "state": {"status": "pending", "input": {"command": "ls"}}},
        }},
        {"type": "message.part.updated", "properties": {
            "part": {"type": "tool", "id": "t1", "callID": "c1", "tool": "bash",
                     "state": {"status": "completed", "input": {"command": "ls"},
                               "output": "file.txt", "title": "ls",
                               "metadata": {}, "time": {"start": 0, "end": 1}}},
        }},
        {"type": "message.part.updated", "properties": {
            "part": {"type": "text", "id": "p1", "text": "Done", "synthetic": False},
            "delta": "Done",
        }},
        {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
    ]

    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse)):
        result = backend.query("run ls", "")

    tool_calls = [e for e in received if isinstance(e, ToolCallEvent)]
    tool_results = [e for e in received if isinstance(e, ToolResultEvent)]
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "bash"
    assert tool_calls[0].arguments == {"command": "ls"}
    assert len(tool_results) == 1
    assert tool_results[0].result == "file.txt"
    assert not tool_results[0].error
    assert result.response == "Done"


def test_query_tool_error_state():
    bus = ConversationBus()
    received: list[object] = []
    bus.subscribe(received.append)

    backend = _make_backend(bus=bus)
    sse = [
        {"type": "message.part.updated", "properties": {
            "part": {"type": "tool", "id": "t1", "callID": "c1", "tool": "bash",
                     "state": {"status": "error", "input": {},
                               "error": "command not found", "time": {"start": 0, "end": 1}}},
        }},
        {"type": "message.part.updated", "properties": {
            "part": {"type": "text", "id": "p1", "text": "Oops", "synthetic": False},
            "delta": "Oops",
        }},
        {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
    ]

    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse)):
        result = backend.query("run bad", "")

    tool_results = [e for e in received if isinstance(e, ToolResultEvent)]
    assert tool_results[0].error is True
    assert tool_results[0].result == "command not found"


# ── query: cost event ─────────────────────────────────────────────────────────


def test_query_cost_event():
    bus = ConversationBus()
    received: list[object] = []
    bus.subscribe(received.append)

    backend = _make_backend(bus=bus)
    sse = [
        {"type": "message.part.updated", "properties": {
            "part": {"type": "text", "id": "p1", "text": "Hi", "synthetic": False},
            "delta": "Hi",
        }},
        {"type": "message.updated", "properties": {
            "info": {"role": "assistant", "tokens": {"input": 10, "output": 20,
                                                      "reasoning": 0, "cache": {"read": 0, "write": 0}}},
        }},
        {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
    ]

    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse)):
        backend.query("hi", "")

    costs = [e for e in received if isinstance(e, CostEvent)]
    assert len(costs) == 1
    assert costs[0].input_tokens == 10
    assert costs[0].output_tokens == 20


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
        {"type": "message.part.updated", "properties": {
            "part": {"type": "text", "id": "p1", "text": "ok", "synthetic": False},
            "delta": "ok",
        }},
        {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
    ]

    posted: list[tuple[str, dict]] = []

    def _urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if "/event" in url:
            return _FakeResp(_make_sse_bytes(*sse))
        # Capture POST bodies
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
        {"type": "message.part.updated", "properties": {
            "part": {"type": "text", "id": "p1", "text": "denied", "synthetic": False},
            "delta": "denied",
        }},
        {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
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
        {"type": "message.part.updated", "properties": {
            "part": {"type": "text", "id": "p1", "text": "pushed", "synthetic": False},
            "delta": "pushed",
        }},
        {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
    ]

    posted: list[tuple[str, dict]] = []

    def _urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if "/event" in url:
            return _FakeResp(_make_sse_bytes(*sse))
        if hasattr(req, "data") and req.data:
            posted.append((url, json.loads(req.data)))
        return _FakeResp(b"{}")

    # Simulate user allowing confirmation 50ms after the event
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
        {"type": "message.part.updated", "properties": {
            "part": {"type": "text", "id": "p1", "text": "not pushed", "synthetic": False},
            "delta": "not pushed",
        }},
        {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
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
        {"type": "message.part.updated", "properties": {
            "part": {"type": "text", "id": "p1", "text": "nope", "synthetic": False},
            "delta": "nope",
        }},
        {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
    ]

    posted: list[tuple[str, dict]] = []

    def _urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if "/event" in url:
            return _FakeResp(_make_sse_bytes(*sse))
        if hasattr(req, "data") and req.data:
            posted.append((url, json.loads(req.data)))
        return _FakeResp(b"{}")

    # Patch timeout to 0.05s so the test doesn't wait 60s
    with patch.object(oc_module, "_CONFIRM_TIMEOUT", 0.05):
        with patch("urllib.request.urlopen", side_effect=_urlopen):
            backend.query("git push", "")

    perm_replies = [(u, b) for u, b in posted if "permissions" in u]
    assert perm_replies[0][1] == {"response": "reject"}


# ── interrupt ─────────────────────────────────────────────────────────────────


def test_interrupt_returns_interrupted_result():
    """interrupt() while streaming blocks → LLMResult with interrupted=True."""
    backend = _make_backend()

    # One event then the stream blocks (simulates a long running turn)
    initial_sse = _make_sse_bytes({"type": "message.part.updated", "properties": {
        "part": {"type": "text", "id": "p1", "text": "...", "synthetic": False},
        "delta": "...",
    }})

    blocking_resp: list[_BlockingFakeResp] = []

    def _urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if "/event" in url:
            resp = _BlockingFakeResp(initial_sse)
            blocking_resp.append(resp)
            return resp
        return _FakeResp(b"{}")

    # interrupt after 30ms — closes the SSE resp, unblocking read()
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
    backend._session_id = None  # no active session

    called = []

    def _urlopen(req, timeout=None):
        called.append(req)
        return _FakeResp(b"{}")

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        backend.reset_session()

    assert not called  # no HTTP calls made


def test_query_creates_session_when_none():
    """First query with no session_id → POST /session to create one."""
    backend = OpenCodeServeBackend(
        policy=PolicyEngine(),
        bus=ConversationBus(),
        cwd="/tmp",
    )
    backend._base_url = "http://localhost:9999"
    # session_expired() returns True → reset_session() is called (no-op since no session)
    # then _create_session() is called

    sse = [
        {"type": "message.part.updated", "properties": {
            "part": {"type": "text", "id": "p1", "text": "hello", "synthetic": False},
            "delta": "hello",
        }},
        {"type": "session.idle", "properties": {"sessionID": "new-sess"}},
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
    backend._session_id = "sess-1"  # keep session id for the test

    sse = [
        {"type": "message.part.updated", "properties": {
            "part": {"type": "text", "id": "p1", "text": "ok", "synthetic": False},
            "delta": "ok",
        }},
        {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
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

    def _urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if "/event" in url:
            return _FakeResp(_make_sse_bytes(*sse))
        if hasattr(req, "data") and req.data:
            try:
                bodies.append(json.loads(req.data))
            except Exception:
                pass
        # Return a new session id for the session creation POST
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
    # _last_interaction is set → session not expired → not a new session

    sse = [
        {"type": "message.part.updated", "properties": {
            "part": {"type": "text", "id": "p1", "text": "ok", "synthetic": False},
            "delta": "ok",
        }},
        {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
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
