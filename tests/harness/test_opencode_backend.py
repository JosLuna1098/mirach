"""Tests for OpenCodeServeBackend — mocked SSE stream, no real opencode server.

Everything here speaks the opencode 2.x wire protocol: routes under /api, an
event envelope of {id, type, created, data}, and REST payloads wrapped in
{"data": [...], "cursor": {...}}.
"""

from __future__ import annotations

import base64
import contextlib
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
    ToolCallEvent,
    ToolResultEvent,
)
from mirach.harness.policy.engine import Decision, PolicyEngine
from mirach.harness.providers.opencode import (
    _SESSION_RULES,
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


def _ev(etype: str, **data: object) -> dict:
    """Build a v2 event envelope."""
    return {"id": "evt_1", "type": etype, "created": 0, "data": data}


def _text_delta(msg_id: str, ordinal: int, delta: str, session_id: str = "sess-1") -> dict:
    return _ev(
        "session.text.delta",
        sessionID=session_id,
        assistantMessageID=msg_id,
        ordinal=ordinal,
        delta=delta,
    )


def _text_ended(msg_id: str, ordinal: int, text: str, session_id: str = "sess-1") -> dict:
    return _ev(
        "session.text.ended",
        sessionID=session_id,
        assistantMessageID=msg_id,
        ordinal=ordinal,
        text=text,
    )


def _exec_started(session_id: str = "sess-1") -> dict:
    return _ev("session.execution.started", sessionID=session_id)


def _exec_succeeded(session_id: str = "sess-1") -> dict:
    return _ev("session.execution.succeeded", sessionID=session_id)


def _assistant_msg(content: list[dict], tokens: dict | None = None) -> dict:
    return {
        "id": "msg-1",
        "type": "assistant",
        "content": content,
        "tokens": tokens
        or {"input": 1, "output": 2, "reasoning": 0, "cache": {"read": 0, "write": 0}},
    }


def _rest_messages(*messages: dict) -> dict:
    return {"data": list(messages), "cursor": {}}


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

    def __enter__(self) -> _FakeResp:
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
    """Return a backend with a pre-set URL, password and session (no subprocess)."""
    backend = OpenCodeServeBackend(
        policy=policy or PolicyEngine(),
        bus=bus or ConversationBus(),
        cwd="/tmp/test",
    )
    backend._base_url = "http://localhost:9999"
    backend._password = "pw"
    backend._session_id = "sess-1"
    backend._last_interaction = time.time()  # prevent session_expired on first call
    return backend


def _mock_urlopen(sse_events: list[dict], rest_responses: dict[str, object] | None = None):
    """
    Build a side_effect function for urllib.request.urlopen.

    GET /api/event → FakeResp with SSE bytes.
    Everything else → FakeResp with JSON from rest_responses[path] or {}.
    """
    rest = rest_responses or {}

    def _side_effect(req_or_url, timeout=None):
        url = req_or_url if isinstance(req_or_url, str) else req_or_url.full_url
        if "/api/event" in url:
            return _FakeResp(_make_sse_bytes(*sse_events))
        for key, payload in rest.items():
            if key in url:
                body = json.dumps(payload).encode() if payload else b""
                return _FakeResp(body)
        return _FakeResp(b"{}")

    return _side_effect


def _recorder(sse_events: list[dict], rest_responses: dict[str, object] | None = None):
    """urlopen side effect that also records every (url, method, body) it sees."""
    seen: list[tuple[str, str, dict | None, dict]] = []
    inner = _mock_urlopen(sse_events, rest_responses)

    def _side_effect(req_or_url, timeout=None):
        if not isinstance(req_or_url, str):
            body = None
            if req_or_url.data:
                with contextlib.suppress(Exception):
                    body = json.loads(req_or_url.data)
            seen.append(
                (req_or_url.full_url, req_or_url.get_method(), body, dict(req_or_url.headers))
            )
        return inner(req_or_url, timeout)

    return _side_effect, seen


# ── _parse_sse unit tests ─────────────────────────────────────────────────────


def test_parse_sse_basic():
    ev = _exec_succeeded()
    resp = _FakeResp(_make_sse_bytes(ev))
    result = list(_parse_sse(resp, threading.Event()))
    assert result == [ev]


def test_parse_sse_multiple_events():
    events = [_text_delta("m1", 0, "Hi"), _exec_succeeded()]
    resp = _FakeResp(_make_sse_bytes(*events))
    result = list(_parse_sse(resp, threading.Event()))
    assert result == events


def test_parse_sse_stops_on_interrupt():
    interrupted = threading.Event()
    interrupted.set()
    resp = _FakeResp(_make_sse_bytes(_exec_succeeded()))
    result = list(_parse_sse(resp, interrupted))
    assert result == []


def test_parse_sse_ignores_malformed_json():
    raw = b'data: not-json\n\ndata: {"type": "ok"}\n\n'
    resp = _FakeResp(raw)
    result = list(_parse_sse(resp, threading.Event()))
    assert result == [{"type": "ok"}]


def test_parse_sse_handles_crlf_line_endings():
    ev = _exec_succeeded()
    crlf_bytes = b"data: " + json.dumps(ev).encode() + b"\r\n\r\n"
    resp = _FakeResp(crlf_bytes)
    result = list(_parse_sse(resp, threading.Event()))
    assert result == [ev]


# ── _opencode_type_to_policy_tool ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "oc_type,expected",
    [
        ("shell", "bash"),
        ("bash", "bash"),
        ("edit", "edit_file"),
        ("webfetch", "web_fetch"),
        ("websearch", "web_search"),
        ("external_directory", "read_file"),
        ("read", "read_file"),
        ("unknown_tool", "unknown_tool"),
    ],
)
def test_type_mapping(oc_type, expected):
    assert _opencode_type_to_policy_tool(oc_type) == expected


# ── transport: auth headers and /api prefix ───────────────────────────────────


def test_every_request_carries_auth_and_directory_headers():
    """Auth is mandatory in v2; the cwd travels in x-opencode-directory."""
    backend = _make_backend()
    sse = [_exec_started(), _text_delta("m1", 0, "ok"), _exec_succeeded()]
    side_effect, seen = _recorder(sse)

    with patch("urllib.request.urlopen", side_effect=side_effect):
        backend.query("hi", "")

    assert seen, "no requests were made"
    expected = "Basic " + base64.b64encode(b"opencode:pw").decode()
    for url, _method, _body, headers in seen:
        assert headers.get("Authorization") == expected
        assert headers.get("X-opencode-directory") == "/tmp/test"
        assert "/api/" in url


# ── query: text streaming ─────────────────────────────────────────────────────


def test_query_text_streaming():
    """Text deltas are emitted as TextDeltaEvents; final text is returned in LLMResult."""
    bus = ConversationBus()
    received: list[object] = []
    bus.subscribe(received.append)

    backend = _make_backend(bus=bus)
    sse = [
        _exec_started(),
        _text_delta("m1", 0, "Hello"),
        _text_delta("m1", 0, " world"),
        _exec_succeeded(),
    ]

    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse)):
        result = backend.query("hi", "")

    assert result.response == "Hello world"
    assert not result.interrupted
    text_deltas = [e for e in received if isinstance(e, TextDeltaEvent)]
    assert [e.delta for e in text_deltas] == ["Hello", " world"]
    assert any(isinstance(e, DoneEvent) for e in received)


def test_query_multiple_parts_concatenated():
    """Deltas from different (messageID, ordinal) parts are concatenated in order."""
    backend = _make_backend()
    sse = [
        _exec_started(),
        _text_delta("m1", 0, "foo"),
        _text_delta("m1", 1, "bar"),
        _exec_succeeded(),
    ]
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse)):
        result = backend.query("hi", "")
    assert result.response == "foobar"


def test_query_text_ended_overrides_accumulated_deltas():
    """session.text.ended carries the whole part — deltas are ephemeral."""
    backend = _make_backend()
    sse = [
        _exec_started(),
        _text_delta("m1", 0, "par"),
        _text_ended("m1", 0, "partial fixed up"),
        _exec_succeeded(),
    ]
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse)):
        result = backend.query("hi", "")
    assert result.response == "partial fixed up"


def test_query_reasoning_deltas_never_reach_the_bus():
    """session.reasoning.* is a separate stream in v2 and must be ignored."""
    bus = ConversationBus()
    received: list[object] = []
    bus.subscribe(received.append)

    backend = _make_backend(bus=bus)
    sse = [
        _exec_started(),
        _ev(
            "session.reasoning.delta",
            sessionID="sess-1",
            assistantMessageID="m1",
            ordinal=0,
            delta="I am thinking about math. ",
        ),
        _text_delta("m1", 1, "8"),
        _exec_succeeded(),
    ]
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse)):
        result = backend.query("4+4?", "")

    assert result.response == "8"
    assert [e.delta for e in received if isinstance(e, TextDeltaEvent)] == ["8"]


def test_query_final_text_comes_from_rest():
    """The REST message store is authoritative when it answers."""
    backend = _make_backend()
    sse = [_exec_started(), _text_delta("m1", 0, "streamed"), _exec_succeeded()]
    rest = {
        "/message": _rest_messages(
            _assistant_msg([{"type": "text", "text": "from rest"}]),
        )
    }
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse, rest)):
        result = backend.query("4+4?", "")
    assert result.response == "from rest"


def test_query_ignores_events_from_other_sessions():
    """The v2 event stream is global — foreign sessions must not leak in."""
    bus = ConversationBus()
    received: list[object] = []
    bus.subscribe(received.append)

    backend = _make_backend(bus=bus)
    sse = [
        _exec_started(),
        _text_delta("mx", 0, "NOT MINE", session_id="other"),
        _exec_succeeded("other"),
        _text_delta("m1", 0, "mine"),
        _exec_succeeded(),
    ]
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse)):
        result = backend.query("hi", "")

    assert result.response == "mine"
    assert [e.delta for e in received if isinstance(e, TextDeltaEvent)] == ["mine"]


def test_query_ignores_stale_terminal_before_turn_starts():
    """A late terminal event from the previous turn must not end this one."""
    backend = _make_backend()
    sse = [
        _ev("session.execution.interrupted", sessionID="sess-1", reason="user"),
        _exec_started(),
        _text_delta("m1", 0, "answer"),
        _exec_succeeded(),
    ]
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse)):
        result = backend.query("hi", "")
    assert result.response == "answer"
    assert not result.interrupted


# ── query: tools ──────────────────────────────────────────────────────────────


def test_query_tool_events_publish_call_and_result():
    """input.started names the tool, called/success produce one pair of events."""
    bus = ConversationBus()
    received: list[object] = []
    bus.subscribe(received.append)

    backend = _make_backend(bus=bus)
    sse = [
        _exec_started(),
        _ev("session.tool.input.started", sessionID="sess-1", id="call-1", name="shell"),
        _ev("session.tool.called", sessionID="sess-1", id="call-1", input={"command": "ls"}),
        _ev(
            "session.tool.success",
            sessionID="sess-1",
            id="call-1",
            content=[{"type": "text", "text": "file1\nfile2"}],
        ),
        _text_delta("m1", 0, "Two files."),
        _exec_succeeded(),
    ]
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse)):
        result = backend.query("list files", "")

    calls = [e for e in received if isinstance(e, ToolCallEvent)]
    results = [e for e in received if isinstance(e, ToolResultEvent)]
    assert len(calls) == 1
    assert calls[0].name == "shell"
    assert calls[0].arguments == {"command": "ls"}
    assert len(results) == 1
    assert results[0].result == "file1\nfile2"
    assert not results[0].error
    assert result.response == "Two files."


def test_query_tool_failed_marks_error():
    bus = ConversationBus()
    received: list[object] = []
    bus.subscribe(received.append)

    backend = _make_backend(bus=bus)
    sse = [
        _exec_started(),
        _ev("session.tool.input.started", sessionID="sess-1", id="call-1", name="shell"),
        _ev("session.tool.called", sessionID="sess-1", id="call-1", input={"command": "ls"}),
        _ev(
            "session.tool.failed",
            sessionID="sess-1",
            id="call-1",
            error={"type": "aborted", "message": "The user declined this tool call"},
        ),
        _text_delta("m1", 0, "ok"),
        _exec_succeeded(),
    ]
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse)):
        backend.query("list files", "")

    results = [e for e in received if isinstance(e, ToolResultEvent)]
    assert len(results) == 1
    assert results[0].error
    assert results[0].result == "The user declined this tool call"


def test_query_publishes_tools_from_rest_when_stream_omits_them():
    """Tool parts missed by the stream are recovered from the REST message store."""
    bus = ConversationBus()
    received: list[object] = []
    bus.subscribe(received.append)
    backend = _make_backend(bus=bus)

    sse = [_exec_started(), _exec_succeeded()]
    rest = {
        "/message": _rest_messages(
            _assistant_msg([{"type": "text", "text": "Ahí está la lista."}]),
            _assistant_msg(
                [
                    {
                        "type": "tool",
                        "id": "call-1",
                        "name": "shell",
                        "state": {
                            "status": "completed",
                            "input": {"command": "ls /tmp"},
                            "content": [{"type": "text", "text": "file1\nfile2"}],
                        },
                    }
                ]
            ),
        )
    }
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse, rest)):
        result = backend.query("list files", "")

    calls = [e for e in received if isinstance(e, ToolCallEvent)]
    results = [e for e in received if isinstance(e, ToolResultEvent)]
    assert len(calls) == 1
    assert calls[0].name == "shell"
    assert calls[0].arguments == {"command": "ls /tmp"}
    assert len(results) == 1
    assert results[0].result == "file1\nfile2"
    assert not results[0].error
    assert result.response == "Ahí está la lista."
    # tool events must be published BEFORE the DoneEvent so clients render the
    # tool cards above the final answer.
    types = [type(e).__name__ for e in received]
    assert types.index("ToolCallEvent") < types.index("DoneEvent")
    assert types.index("ToolResultEvent") < types.index("DoneEvent")


def test_rest_tools_are_not_republished_on_the_next_turn():
    """Dedup sets live on the instance; reset_session() clears them."""
    bus = ConversationBus()
    received: list[object] = []
    bus.subscribe(received.append)
    backend = _make_backend(bus=bus)

    sse = [_exec_started(), _text_delta("m1", 0, "ok"), _exec_succeeded()]
    rest = {
        "/message": _rest_messages(
            _assistant_msg(
                [
                    {"type": "text", "text": "ok"},
                    {
                        "type": "tool",
                        "id": "call-1",
                        "name": "shell",
                        "state": {
                            "status": "completed",
                            "input": {"command": "ls"},
                            "content": [{"type": "text", "text": "out"}],
                        },
                    },
                ]
            ),
        )
    }
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse, rest)):
        backend.query("turn one", "")
        backend.query("turn two", "")

    assert len([e for e in received if isinstance(e, ToolCallEvent)]) == 1
    assert len([e for e in received if isinstance(e, ToolResultEvent)]) == 1

    with patch("urllib.request.urlopen", side_effect=_mock_urlopen([], {})):
        backend.reset_session()
    assert backend._tool_called == set()
    assert backend._tool_resulted == set()


# ── query: execution failure ──────────────────────────────────────────────────


def test_query_execution_failed_publishes_error():
    bus = ConversationBus()
    received: list[object] = []
    bus.subscribe(received.append)

    backend = _make_backend(bus=bus)
    sse = [
        _exec_started(),
        _ev(
            "session.execution.failed",
            sessionID="sess-1",
            error={"type": "provider.no-route", "message": "Model unavailable: x/y"},
        ),
    ]

    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse)):
        result = backend.query("hi", "")

    errors = [e for e in received if isinstance(e, ErrorEvent)]
    assert len(errors) == 1
    assert "Model unavailable" in errors[0].message
    assert not result.interrupted
    assert result.response  # generic_error string


# ── permissions ───────────────────────────────────────────────────────────────


def _permission_event(
    action: str = "shell",
    resources: list[str] | None = None,
    perm_id: str = "per-1",
    **extra: object,
) -> dict:
    return _ev(
        "permission.asked",
        id=perm_id,
        sessionID="sess-1",
        action=action,
        resources=resources if resources is not None else ["ls"],
        source={"type": "tool", "messageID": "m1", "id": "call-1"},
        **extra,
    )


def test_permission_allow():
    """PolicyEngine ALLOW → reply "once" immediately."""
    policy = MagicMock(spec=PolicyEngine)
    policy.check.return_value = Decision.ALLOW

    backend = _make_backend(policy=policy)
    sse = [_exec_started(), _permission_event(), _text_delta("m1", 0, "ok"), _exec_succeeded()]
    side_effect, seen = _recorder(sse)

    with patch("urllib.request.urlopen", side_effect=side_effect):
        backend.query("list files", "")

    policy.check.assert_called_once_with("bash", {"command": "ls"})
    replies = [(u, b) for u, _m, b, _h in seen if "/permission/per-1/reply" in u]
    assert replies and replies[0][1] == {"decision": "once"}


def test_permission_deny():
    policy = MagicMock(spec=PolicyEngine)
    policy.check.return_value = Decision.DENY

    backend = _make_backend(policy=policy)
    sse = [
        _exec_started(),
        _permission_event(resources=["rm -rf /"]),
        _text_delta("m1", 0, "denied"),
        _exec_succeeded(),
    ]
    side_effect, seen = _recorder(sse)

    with patch("urllib.request.urlopen", side_effect=side_effect):
        backend.query("delete everything", "")

    replies = [(u, b) for u, _m, b, _h in seen if "/permission/per-1/reply" in u]
    assert replies and replies[0][1] == {"decision": "reject"}


def test_policy_denial_answers_plainly_instead_of_model_text():
    """opencode 2.x ends the turn on a rejection; whatever the model said before
    ("I'll delete it…") must not be spoken as if the action happened."""
    policy = MagicMock(spec=PolicyEngine)
    policy.check.return_value = Decision.DENY

    backend = _make_backend(policy=policy)
    sse = [
        _exec_started(),
        _text_delta("m1", 0, "Claro, lo borro ahora."),
        _permission_event(resources=["rm -rf /"]),
        _ev("session.execution.interrupted", sessionID="sess-1", reason="shutdown"),
    ]
    side_effect, _seen = _recorder(sse)

    with patch("urllib.request.urlopen", side_effect=side_effect):
        result = backend.query("delete everything", "")

    from mirach import i18n

    assert result.response == i18n.t("action_blocked")
    assert not result.interrupted


def test_user_denial_answers_plainly(monkeypatch):
    policy = MagicMock(spec=PolicyEngine)
    policy.check.return_value = Decision.CONFIRM

    backend = _make_backend(policy=policy)
    sse = [
        _exec_started(),
        _permission_event(resources=["rm notas.txt"]),
        _ev("session.execution.interrupted", sessionID="sess-1", reason="shutdown"),
    ]
    side_effect, seen = _recorder(sse)

    # Answer "no" shortly after the confirmation is requested — from another
    # thread, as the real clients do (the handler clears the event before waiting).
    def _deny_later(e: object) -> None:
        if getattr(e, "type", "") == "awaiting_confirmation":
            threading.Timer(0.05, backend.deny, args=("x",)).start()

    backend._bus.subscribe(_deny_later)

    with patch("urllib.request.urlopen", side_effect=side_effect):
        result = backend.query("borra notas", "")

    from mirach import i18n

    assert result.response == i18n.t("action_denied")
    replies = [b for u, _m, b, _h in seen if "/permission/per-1/reply" in u]
    assert replies == [{"decision": "reject"}]


def test_permission_multiple_resources_takes_strictest():
    """One DENY among several resources rejects the whole request."""
    policy = MagicMock(spec=PolicyEngine)
    policy.check.side_effect = [Decision.ALLOW, Decision.DENY]

    backend = _make_backend(policy=policy)
    sse = [
        _exec_started(),
        _permission_event(resources=["ls", "rm -rf /"]),
        _text_delta("m1", 0, "no"),
        _exec_succeeded(),
    ]
    side_effect, seen = _recorder(sse)

    with patch("urllib.request.urlopen", side_effect=side_effect):
        backend.query("do things", "")

    assert policy.check.call_count == 2
    replies = [(u, b) for u, _m, b, _h in seen if "/permission/per-1/reply" in u]
    assert replies and replies[0][1] == {"decision": "reject"}


def test_permission_confirm_keeps_bash_name_on_the_wire():
    """A CONFIRM on action "shell" is published to clients as "bash"."""
    policy = MagicMock(spec=PolicyEngine)
    policy.check.side_effect = [Decision.CONFIRM, Decision.ALLOW]

    bus = ConversationBus()
    received: list[object] = []
    bus.subscribe(received.append)
    backend = _make_backend(policy=policy, bus=bus)

    sse = [
        _exec_started(),
        _permission_event(resources=["git push", "ls"]),
        _text_delta("m1", 0, "pushed"),
        _exec_succeeded(),
    ]
    side_effect, seen = _recorder(sse)

    def _allow_after_delay():
        time.sleep(0.05)
        backend.reply_confirmation(allow=True)

    threading.Thread(target=_allow_after_delay, daemon=True).start()

    with patch("urllib.request.urlopen", side_effect=side_effect):
        backend.query("git push", "")

    confirms = [e for e in received if isinstance(e, AwaitingConfirmationEvent)]
    assert len(confirms) == 1
    assert confirms[0].name == "bash"
    assert confirms[0].tool_call_id == "call-1"
    assert confirms[0].arguments["pattern"] == "git push; ls"

    replies = [(u, b) for u, _m, b, _h in seen if "/permission/per-1/reply" in u]
    assert replies and replies[0][1] == {"decision": "once"}


def test_permission_confirm_user_denies():
    policy = MagicMock(spec=PolicyEngine)
    policy.check.return_value = Decision.CONFIRM

    backend = _make_backend(policy=policy)
    sse = [
        _exec_started(),
        _permission_event(resources=["git push"]),
        _text_delta("m1", 0, "not pushed"),
        _exec_succeeded(),
    ]
    side_effect, seen = _recorder(sse)

    def _deny_after_delay():
        time.sleep(0.05)
        backend.reply_confirmation(allow=False)

    threading.Thread(target=_deny_after_delay, daemon=True).start()

    with patch("urllib.request.urlopen", side_effect=side_effect):
        backend.query("git push", "")

    replies = [(u, b) for u, _m, b, _h in seen if "/permission/per-1/reply" in u]
    assert replies and replies[0][1] == {"decision": "reject"}


def test_permission_confirm_timeout():
    import mirach.harness.providers.opencode as oc_module

    policy = MagicMock(spec=PolicyEngine)
    policy.check.return_value = Decision.CONFIRM

    backend = _make_backend(policy=policy)
    sse = [
        _exec_started(),
        _permission_event(resources=["git push"]),
        _text_delta("m1", 0, "nope"),
        _exec_succeeded(),
    ]
    side_effect, seen = _recorder(sse)

    with (
        patch.object(oc_module, "_CONFIRM_TIMEOUT", 0.05),
        patch("urllib.request.urlopen", side_effect=side_effect),
    ):
        backend.query("git push", "")

    replies = [(u, b) for u, _m, b, _h in seen if "/permission/per-1/reply" in u]
    assert replies and replies[0][1] == {"decision": "reject"}


def test_permission_external_directory_strips_glob_suffix():
    policy = MagicMock(spec=PolicyEngine)
    policy.check.return_value = Decision.ALLOW

    backend = _make_backend(policy=policy)
    sse = [
        _exec_started(),
        _permission_event(action="external_directory", resources=["/x/y/*"]),
        _text_delta("m1", 0, "ok"),
        _exec_succeeded(),
    ]

    with patch("urllib.request.urlopen", side_effect=_mock_urlopen(sse)):
        backend.query("read there", "")

    policy.check.assert_called_once_with("read_file", {"path": "/x/y"})


# ── forms ─────────────────────────────────────────────────────────────────────


def test_form_created_is_cancelled():
    """The harness is headless: any form that opens is dismissed."""
    backend = _make_backend()
    sse = [
        _exec_started(),
        _ev("form.created", form={"id": "frm_1", "sessionID": "sess-1"}),
        _text_delta("m1", 0, "ok"),
        _exec_succeeded(),
    ]
    side_effect, seen = _recorder(sse)

    with patch("urllib.request.urlopen", side_effect=side_effect):
        backend.query("ask me", "")

    deletes = [u for u, m, _b, _h in seen if m == "DELETE"]
    assert any(u.endswith("/api/session/sess-1/form/frm_1") for u in deletes)


def test_form_from_another_session_is_left_alone():
    backend = _make_backend()
    sse = [
        _exec_started(),
        _ev("form.created", form={"id": "frm_1", "sessionID": "other"}),
        _text_delta("m1", 0, "ok"),
        _exec_succeeded(),
    ]
    side_effect, seen = _recorder(sse)

    with patch("urllib.request.urlopen", side_effect=side_effect):
        backend.query("ask me", "")

    assert not [u for u, m, _b, _h in seen if m == "DELETE"]


# ── interrupt ─────────────────────────────────────────────────────────────────


def test_interrupt_returns_interrupted_result():
    """interrupt() while streaming blocks → LLMResult with interrupted=True."""
    backend = _make_backend()

    initial_sse = _make_sse_bytes(_exec_started(), _text_delta("m1", 0, "..."))

    blocking_resp: list[_BlockingFakeResp] = []

    def _urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if "/api/event" in url:
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


def test_interrupt_posts_to_the_interrupt_route_without_body():
    backend = _make_backend()
    side_effect, seen = _recorder([])

    with patch("urllib.request.urlopen", side_effect=side_effect):
        backend.interrupt()

    posts = [(u, b) for u, m, b, _h in seen if m == "POST"]
    assert posts == [("http://localhost:9999/api/session/sess-1/interrupt", None)]


def test_compact_posts_to_the_compact_route():
    backend = _make_backend()
    backend._session_tokens = 999
    side_effect, seen = _recorder([])

    with patch("urllib.request.urlopen", side_effect=side_effect):
        backend._compact()

    posts = [(u, b) for u, m, b, _h in seen if m == "POST"]
    assert posts == [("http://localhost:9999/api/session/sess-1/compact", {})]
    assert backend._session_tokens == 0


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
    backend = _make_backend()
    side_effect, seen = _recorder([])

    with patch("urllib.request.urlopen", side_effect=side_effect):
        backend.reset_session()

    assert backend._session_id is None
    deletes = [u for u, m, _b, _h in seen if m == "DELETE"]
    assert deletes == ["http://localhost:9999/api/session/sess-1"]


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


def test_create_session_sends_rules_model_and_location():
    backend = OpenCodeServeBackend(
        policy=PolicyEngine(),
        bus=ConversationBus(),
        cwd="/tmp",
        provider_id="opencode",
        model_id="big-pickle",
    )
    backend._base_url = "http://localhost:9999"
    backend._password = "pw"

    sse = [
        _exec_started("new-sess"),
        _text_delta("m1", 0, "hello", "new-sess"),
        _exec_succeeded("new-sess"),
    ]

    def _urlopen(req, timeout=None):
        url = req.full_url
        if "/api/event" in url:
            return _FakeResp(_make_sse_bytes(*sse))
        if url.endswith("/api/session") and req.get_method() == "POST":
            bodies.append(json.loads(req.data))
            return _FakeResp(json.dumps({"data": {"id": "new-sess"}}).encode())
        return _FakeResp(b"{}")

    bodies: list[dict] = []
    with patch("urllib.request.urlopen", side_effect=_urlopen):
        result = backend.query("hi", "")

    assert backend._session_id == "new-sess"
    assert result.response == "hello"
    assert len(bodies) == 1
    assert bodies[0]["permissions"] == _SESSION_RULES
    assert bodies[0]["location"] == {"directory": "/tmp"}
    assert bodies[0]["model"] == {"providerID": "opencode", "id": "big-pickle"}


def test_create_session_omits_model_when_not_configured():
    backend = OpenCodeServeBackend(policy=PolicyEngine(), bus=ConversationBus(), cwd="/tmp")
    backend._base_url = "http://localhost:9999"
    backend._password = "pw"

    bodies: list[dict] = []

    def _urlopen(req, timeout=None):
        bodies.append(json.loads(req.data))
        return _FakeResp(json.dumps({"data": {"id": "s"}}).encode())

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        backend._create_session()

    assert "model" not in bodies[0]


def test_create_session_404_explains_the_version_requirement():
    import urllib.error

    backend = _make_backend()

    def _urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, io.BytesIO(b""))

    with (
        patch("urllib.request.urlopen", side_effect=_urlopen),
        pytest.raises(RuntimeError, match="requires opencode >= 2.0"),
    ):
        backend._create_session()


# ── new session: system prompt via instruction entries ───────────────────────


def _new_session_backend() -> OpenCodeServeBackend:
    backend = _make_backend()
    backend._last_interaction = 0.0  # force new session
    return backend


def _instruction_recorder(sse: list[dict], put_fails: bool = False):
    seen: list[tuple[str, str, dict | None]] = []

    def _urlopen(req, timeout=None):
        import urllib.error

        url = req.full_url
        method = req.get_method()
        body = None
        if req.data:
            with contextlib.suppress(Exception):
                body = json.loads(req.data)
        if "/api/event" in url:
            return _FakeResp(_make_sse_bytes(*sse))
        seen.append((url, method, body))
        if method == "PUT" and put_fails:
            raise urllib.error.HTTPError(url, 500, "boom", {}, io.BytesIO(b"{}"))
        if url.endswith("/api/session") and method == "POST":
            return _FakeResp(json.dumps({"data": {"id": "sess-1"}}).encode())
        return _FakeResp(b"{}")

    return _urlopen, seen


def test_new_session_sends_instructions_and_keeps_the_prompt_clean():
    backend = _new_session_backend()
    sse = [_exec_started(), _text_delta("m1", 0, "ok"), _exec_succeeded()]
    urlopen, seen = _instruction_recorder(sse)

    with patch("urllib.request.urlopen", side_effect=urlopen):
        backend.query("hi", system_prompt="Be helpful.", obsidian_context="Remember X.")

    puts = [(u, b) for u, m, b in seen if m == "PUT"]
    assert len(puts) == 1
    assert puts[0][0].endswith(
        "/api/experimental/session/sess-1/instructions/entries/mirach-system"
    )
    value = puts[0][1]["value"]
    assert "Be helpful." in value
    assert "Remember X." in value

    prompts = [b for u, m, b in seen if u.endswith("/prompt")]
    assert prompts == [{"text": "hi"}]


def test_new_session_falls_back_to_prefix_when_the_put_fails():
    backend = _new_session_backend()
    sse = [_exec_started(), _text_delta("m1", 0, "ok"), _exec_succeeded()]
    urlopen, seen = _instruction_recorder(sse, put_fails=True)

    with patch("urllib.request.urlopen", side_effect=urlopen):
        backend.query("hi", system_prompt="Be helpful.")

    prompts = [b for u, m, b in seen if u.endswith("/prompt")]
    assert len(prompts) == 1
    assert prompts[0]["text"].startswith("Follow these instructions for the ENTIRE conversation:")
    assert prompts[0]["text"].endswith("hi")


def test_instruction_entries_can_be_switched_off(monkeypatch):
    import mirach.harness.providers.opencode as oc_module

    monkeypatch.setattr(oc_module, "_USE_INSTRUCTION_ENTRIES", False)
    backend = _new_session_backend()
    sse = [_exec_started(), _text_delta("m1", 0, "ok"), _exec_succeeded()]
    urlopen, seen = _instruction_recorder(sse)

    with patch("urllib.request.urlopen", side_effect=urlopen):
        backend.query("hi", system_prompt="Be helpful.")

    assert not [u for u, m, _b in seen if m == "PUT"]
    prompts = [b for u, m, b in seen if u.endswith("/prompt")]
    assert prompts[0]["text"].startswith("Follow these instructions for the ENTIRE conversation:")


def test_existing_session_neither_puts_nor_prefixes():
    backend = _make_backend()  # not expired
    sse = [_exec_started(), _text_delta("m1", 0, "ok"), _exec_succeeded()]
    urlopen, seen = _instruction_recorder(sse)

    with patch("urllib.request.urlopen", side_effect=urlopen):
        backend.query("hi", system_prompt="Be helpful.")

    assert not [u for u, m, _b in seen if m == "PUT"]
    prompts = [b for u, m, b in seen if u.endswith("/prompt")]
    assert prompts == [{"text": "hi"}]


# ── start(): password plumbing ────────────────────────────────────────────────


def test_start_parses_the_listen_line_and_passes_the_password(monkeypatch):
    monkeypatch.setenv("OPENCODE_SERVER_PASSWORD", "stale-v1-value")
    backend = OpenCodeServeBackend(policy=PolicyEngine(), bus=ConversationBus(), cwd="/tmp")

    fake_proc = MagicMock()
    fake_proc.stdout.readline.side_effect = ["server listening on http://127.0.0.1:5555\n"]
    fake_proc.poll.return_value = None
    fake_proc.stdout.__iter__ = lambda _self: iter(())

    captured: dict = {}

    def _popen(args, **kwargs):
        captured.update(kwargs)
        captured["args"] = args
        return fake_proc

    with patch("subprocess.Popen", side_effect=_popen):
        backend.start()

    assert backend._base_url == "http://127.0.0.1:5555"
    env = captured["env"]
    assert env["OPENCODE_PASSWORD"] == backend._password
    assert backend._password
    assert "OPENCODE_SERVER_PASSWORD" not in env
