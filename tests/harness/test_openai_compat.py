"""Unit tests for OpenAICompatProvider — no network, urllib.request is patched."""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from mirach.harness.providers.base import Message, ToolCall, ToolDef
from mirach.harness.providers.openai_compat import (
    OpenAICompatProvider,
    _msg_to_wire,
    _tooldef_to_wire,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _fake_response(body: dict[str, Any]) -> MagicMock:
    """Return a context-manager mock that reads a JSON body."""
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = json.dumps(body).encode()
    return mock


def _choices(content: str = "", tool_calls: list | None = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {
        "choices": [{"message": msg, "finish_reason": "stop" if not tool_calls else "tool_calls"}]
    }


def _make_provider(**kwargs: Any) -> OpenAICompatProvider:
    return OpenAICompatProvider(model="test-model", **kwargs)


# ── payload construction ──────────────────────────────────────────────────────


class TestBuildPayload:
    def test_model_and_temperature_present(self):
        p = _make_provider(temperature=0.5)
        payload = p._build_payload([], [], {})
        assert payload["model"] == "test-model"
        assert payload["temperature"] == 0.5

    def test_num_ctx_injected_under_options(self):
        p = _make_provider(num_ctx=65536)
        payload = p._build_payload([], [], {})
        assert payload["options"]["num_ctx"] == 65536

    def test_tools_absent_when_empty(self):
        p = _make_provider()
        payload = p._build_payload([], [], {})
        assert "tools" not in payload
        assert "tool_choice" not in payload

    def test_tools_present_when_given(self):
        p = _make_provider()
        tools = [
            ToolDef(
                name="foo", description="does foo", parameters={"type": "object", "properties": {}}
            )
        ]
        payload = p._build_payload([], tools, {})
        assert len(payload["tools"]) == 1
        assert payload["tool_choice"] == "auto"
        assert payload["tools"][0]["function"]["name"] == "foo"

    def test_ctx_overrides_merged(self):
        p = _make_provider()
        payload = p._build_payload([], [], {"format": {"type": "object"}})
        assert payload["format"] == {"type": "object"}


# ── response parsing ──────────────────────────────────────────────────────────


class TestParseResponse:
    def test_simple_text_stop(self):
        p = _make_provider()
        data = _choices(content="Hello there")
        resp = p._parse(data)
        assert resp.content == "Hello there"
        assert resp.stop_reason == "stop"
        assert resp.tool_calls == []

    def test_tool_call_parsed(self):
        p = _make_provider()
        data = _choices(
            tool_calls=[
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "bash", "arguments": '{"command": "ls"}'},
                }
            ]
        )
        resp = p._parse(data)
        assert resp.stop_reason == "tool_use"
        assert len(resp.tool_calls) == 1
        tc = resp.tool_calls[0]
        assert tc.id == "call_abc"
        assert tc.name == "bash"
        assert tc.arguments == {"command": "ls"}

    def test_tool_call_arguments_already_dict(self):
        """Some endpoints return arguments as a dict instead of a JSON string."""
        p = _make_provider()
        data = _choices(
            tool_calls=[
                {
                    "id": "call_xyz",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": {"path": "/tmp/a"}},
                }
            ]
        )
        resp = p._parse(data)
        assert resp.tool_calls[0].arguments == {"path": "/tmp/a"}

    def test_empty_tool_calls_list_is_stop(self):
        p = _make_provider()
        data = _choices(content="done", tool_calls=[])
        resp = p._parse(data)
        assert resp.stop_reason == "stop"


# ── full send() round-trip (urllib patched) ───────────────────────────────────


class TestSend:
    def test_send_returns_response(self):
        p = _make_provider(base_url="http://localhost:11434")
        fake = _fake_response(_choices(content="world"))

        with patch("urllib.request.urlopen", return_value=fake):
            resp = p.send(
                [Message(role="user", content="hello")],
                [],
            )
        assert resp.content == "world"

    def test_authorization_header_set(self):
        p = _make_provider(api_key="sk-test")
        fake = _fake_response(_choices(content="ok"))
        captured: list = []

        def mock_urlopen(req, timeout=None):
            captured.append(req)
            return fake

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            p.send([Message(role="user", content="hi")], [])

        assert captured[0].get_header("Authorization") == "Bearer sk-test"

    def test_http_error_raises_runtime_error(self):
        import urllib.error

        p = _make_provider()
        err = urllib.error.HTTPError(
            url="http://x", code=400, msg="Bad Request", hdrs=None, fp=BytesIO(b"bad input")
        )

        with (
            patch("urllib.request.urlopen", side_effect=err),
            pytest.raises(RuntimeError, match="HTTP 400"),
        ):
            p.send([Message(role="user", content="hi")], [])

    def test_ctx_forwarded_in_payload(self):
        p = _make_provider()
        fake = _fake_response(_choices(content="ok"))
        captured_body: list[dict] = []

        def mock_urlopen(req, timeout=None):
            captured_body.append(json.loads(req.data))
            return fake

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            p.send(
                [Message(role="user", content="hi")],
                [],
                ctx={"format": {"type": "object"}},
            )

        assert captured_body[0]["format"] == {"type": "object"}


# ── wire-format helpers ───────────────────────────────────────────────────────


class TestWireHelpers:
    def test_user_message(self):
        m = Message(role="user", content="hi")
        assert _msg_to_wire(m) == {"role": "user", "content": "hi"}

    def test_tool_result_message(self):
        m = Message(role="tool", content="42", tool_call_id="call_1")
        wire = _msg_to_wire(m)
        assert wire == {"role": "tool", "tool_call_id": "call_1", "content": "42"}

    def test_assistant_with_tool_calls(self):
        m = Message(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="call_1", name="bash", arguments={"command": "ls"})],
        )
        wire = _msg_to_wire(m)
        assert wire["role"] == "assistant"
        assert len(wire["tool_calls"]) == 1
        assert wire["tool_calls"][0]["id"] == "call_1"
        assert json.loads(wire["tool_calls"][0]["function"]["arguments"]) == {"command": "ls"}

    def test_tooldef_wire_shape(self):
        t = ToolDef(
            name="bash",
            description="Run a shell command",
            parameters={"type": "object", "properties": {"command": {"type": "string"}}},
        )
        wire = _tooldef_to_wire(t)
        assert wire["type"] == "function"
        assert wire["function"]["name"] == "bash"
        assert wire["function"]["description"] == "Run a shell command"
