"""Tests for ToolProtocol: prompted, native, parse-repair, auto."""

from __future__ import annotations

import json

import pytest

from mirach.harness.providers.base import Message, Response, ToolCall, ToolDef
from mirach.harness.providers.mock import MockProvider
from mirach.harness.tool_protocol import (
    PreparedTurn,
    PromptedParseError,
    ToolProtocol,
    _add_repair_context,
    _parse_prompted,
    _render_tools,
)

# ── fixtures ──────────────────────────────────────────────────────────────────

TOOLS = [
    ToolDef(
        name="bash",
        description="Run a shell command",
        parameters={"type": "object", "properties": {"command": {"type": "string"}}},
    ),
    ToolDef(
        name="read_file",
        description="Read a file",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
    ),
]

USER_MSG = [Message(role="user", content="list /tmp")]


def _stop(text: str) -> Response:
    return Response(content=text, stop_reason="stop")


def _prompted_stop(action_json: dict) -> Response:
    return Response(content=json.dumps(action_json), stop_reason="stop")


# ── _render_tools ─────────────────────────────────────────────────────────────


class TestRenderTools:
    def test_includes_all_tool_names(self):
        rendered = _render_tools(TOOLS)
        assert "bash" in rendered
        assert "read_file" in rendered

    def test_includes_descriptions(self):
        rendered = _render_tools(TOOLS)
        assert "Run a shell command" in rendered

    def test_empty_tools(self):
        assert _render_tools([]) == ""


# ── _parse_prompted ───────────────────────────────────────────────────────────


class TestParsePrompted:
    def test_final_answer(self):
        resp = Response(
            content='{"action": "final_answer", "answer": "Hello world"}',
            stop_reason="stop",
        )
        result = _parse_prompted(resp)
        assert result.stop_reason == "stop"
        assert result.content == "Hello world"
        assert result.tool_calls == []

    def test_tool_call(self):
        resp = Response(
            content='{"action": "tool_call", "tool": "bash", "arguments": {"command": "ls"}}',
            stop_reason="stop",
        )
        result = _parse_prompted(resp)
        assert result.stop_reason == "tool_use"
        assert len(result.tool_calls) == 1
        tc = result.tool_calls[0]
        assert tc.name == "bash"
        assert tc.arguments == {"command": "ls"}

    def test_tool_call_id_is_deterministic_for_same_input(self):
        raw = '{"action": "tool_call", "tool": "bash", "arguments": {"command": "ls"}}'
        r1 = _parse_prompted(Response(content=raw, stop_reason="stop"))
        r2 = _parse_prompted(Response(content=raw, stop_reason="stop"))
        assert r1.tool_calls[0].id == r2.tool_calls[0].id

    def test_strips_markdown_code_fence(self):
        resp = Response(
            content='```json\n{"action": "final_answer", "answer": "hi"}\n```',
            stop_reason="stop",
        )
        result = _parse_prompted(resp)
        assert result.content == "hi"

    def test_invalid_json_raises_parse_error(self):
        resp = Response(content="not json at all", stop_reason="stop")
        with pytest.raises(PromptedParseError) as exc_info:
            _parse_prompted(resp)
        assert exc_info.value.raw == "not json at all"

    def test_unknown_action_raises_parse_error(self):
        resp = Response(content='{"action": "magic"}', stop_reason="stop")
        with pytest.raises(PromptedParseError, match="Unknown action"):
            _parse_prompted(resp)

    def test_non_dict_arguments_raises_parse_error(self):
        resp = Response(
            content='{"action": "tool_call", "tool": "bash", "arguments": "oops"}',
            stop_reason="stop",
        )
        with pytest.raises(PromptedParseError, match="object"):
            _parse_prompted(resp)


# ── ToolProtocol.prepare ─────────────────────────────────────────────────────


class TestPrepareNative:
    def test_native_pass_through(self):
        p = ToolProtocol(mode="native")
        prepared = p.prepare(USER_MSG, TOOLS)
        assert prepared.messages is USER_MSG
        assert prepared.tools is TOOLS
        assert prepared.ctx == {}

    def test_native_no_tools_pass_through(self):
        p = ToolProtocol(mode="native")
        prepared = p.prepare(USER_MSG, [])
        assert prepared.tools == []
        assert prepared.ctx == {}


class TestPreparePrompted:
    def test_tools_cleared(self):
        p = ToolProtocol(mode="prompted")
        prepared = p.prepare(USER_MSG, TOOLS)
        assert prepared.tools == []

    def test_format_schema_in_ctx(self):
        p = ToolProtocol(mode="prompted")
        prepared = p.prepare(USER_MSG, TOOLS)
        assert "format" in prepared.ctx

    def test_no_format_schema_when_no_tools(self):
        p = ToolProtocol(mode="prompted")
        prepared = p.prepare(USER_MSG, [])
        assert "format" not in prepared.ctx

    def test_system_message_injected(self):
        p = ToolProtocol(mode="prompted")
        prepared = p.prepare(USER_MSG, TOOLS)
        assert prepared.messages[0].role == "system"
        assert "bash" in prepared.messages[0].content

    def test_existing_system_message_merged(self):
        msgs = [Message(role="system", content="You are helpful."), *USER_MSG]
        p = ToolProtocol(mode="prompted")
        prepared = p.prepare(msgs, TOOLS)
        assert prepared.messages[0].role == "system"
        assert "You are helpful." in prepared.messages[0].content
        assert "bash" in prepared.messages[0].content
        # Original system message not duplicated
        assert len([m for m in prepared.messages if m.role == "system"]) == 1

    def test_user_messages_preserved(self):
        p = ToolProtocol(mode="prompted")
        prepared = p.prepare(USER_MSG, TOOLS)
        user_msgs = [m for m in prepared.messages if m.role == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0].content == "list /tmp"


# ── ToolProtocol.send_with_repair ─────────────────────────────────────────────


class TestSendWithRepair:
    def test_native_happy_path(self):
        tc = ToolCall(id="c1", name="bash", arguments={"command": "ls"})
        provider = MockProvider([Response(content="", stop_reason="tool_use", tool_calls=[tc])])
        p = ToolProtocol(mode="native")
        resp = p.send_with_repair(provider, USER_MSG, TOOLS)
        assert resp.stop_reason == "tool_use"
        assert resp.tool_calls[0].name == "bash"

    def test_prompted_happy_path(self):
        provider = MockProvider([_prompted_stop({"action": "final_answer", "answer": "ok"})])
        p = ToolProtocol(mode="prompted")
        resp = p.send_with_repair(provider, USER_MSG, TOOLS)
        assert resp.content == "ok"
        assert resp.stop_reason == "stop"

    def test_prompted_parse_repair_succeeds_on_second_attempt(self):
        """First response: invalid JSON. Second response: valid. Loop recovers."""
        bad = Response(content="oops not json", stop_reason="stop")
        good = Response(
            content='{"action": "final_answer", "answer": "fixed"}',
            stop_reason="stop",
        )
        provider = MockProvider([bad, good])
        p = ToolProtocol(mode="prompted")
        resp = p.send_with_repair(provider, USER_MSG, TOOLS)
        assert resp.content == "fixed"

    def test_prompted_parse_repair_exhausted_raises(self):
        """Three consecutive bad responses exhaust retries and raise PromptedParseError."""
        bad = Response(content="not json", stop_reason="stop")
        provider = MockProvider([bad, bad, bad])
        p = ToolProtocol(mode="prompted")
        with pytest.raises(PromptedParseError):
            p.send_with_repair(provider, USER_MSG, TOOLS)

    def test_repair_message_includes_error_and_raw_output(self):
        exc = PromptedParseError("JSON decode failed", raw="garbage")
        base = PreparedTurn(messages=USER_MSG, tools=TOOLS)
        repaired = _add_repair_context(base, exc)
        repair_msg = repaired.messages[-1]
        assert repair_msg.role == "user"
        assert "JSON decode failed" in repair_msg.content
        assert "garbage" in repair_msg.content

    def test_repair_preserves_ctx(self):
        exc = PromptedParseError("bad", raw="x")
        ctx = {"format": {"type": "object"}}
        base = PreparedTurn(messages=USER_MSG, tools=[], ctx=ctx)
        repaired = _add_repair_context(base, exc)
        assert repaired.ctx == ctx


# ── auto mode ─────────────────────────────────────────────────────────────────


class TestAutoMode:
    def test_auto_with_tools_uses_native(self):
        """auto + tools → native path (tools passed to provider)."""
        p = ToolProtocol(mode="auto")
        prepared = p.prepare(USER_MSG, TOOLS)
        # Native: tools passed through
        assert prepared.tools == TOOLS

    def test_auto_no_tools_still_native(self):
        """auto with no tools uses native mode (plain completion)."""
        p = ToolProtocol(mode="auto")
        prepared = p.prepare(USER_MSG, [])
        assert prepared.tools == []
        assert prepared.ctx == {}
