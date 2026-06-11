"""Tests for NativeBackend adapter and build_native_backend factory."""

from __future__ import annotations

import time

from mirach import config
from mirach.harness.build import build_native_backend
from mirach.harness.events import ConversationBus
from mirach.harness.loop import AgentLoop
from mirach.harness.native_backend import NativeBackend, _build_system
from mirach.harness.providers.base import Response, ToolCall, ToolDef
from mirach.harness.providers.mock import MockProvider
from mirach.harness.tools.registry import ToolRegistry
from mirach.llm_types import LLMBackend, LLMResult

# ── helpers ───────────────────────────────────────────────────────────────────


def _stop(text: str = "done") -> Response:
    return Response(content=text, stop_reason="stop")


def _tool_resp(tc_id: str, name: str, args: dict | None = None) -> Response:
    return Response(
        content="",
        stop_reason="tool_use",
        tool_calls=[ToolCall(id=tc_id, name=name, arguments=args or {})],
    )


def _make_backend(
    responses: list[Response],
    tools: dict[str, str] | None = None,
    speak_filler=None,
) -> NativeBackend:
    provider = MockProvider(responses)
    registry = ToolRegistry()
    if tools:
        for name, retval in tools.items():

            def make_fn(rv):
                return lambda _args: rv

            registry.register(ToolDef(name=name, description="", parameters={}), make_fn(retval))
    bus = ConversationBus()
    loop = AgentLoop(provider=provider, registry=registry, bus=bus)
    return NativeBackend(loop=loop, speak_filler=speak_filler)


# ── LLMResult shape ───────────────────────────────────────────────────────────


class TestQueryReturnsLLMResult:
    def test_returns_llm_result_instance(self):
        backend = _make_backend([_stop("Hello")])
        result = backend.query("hi", "")
        assert isinstance(result, LLMResult)

    def test_response_text_is_populated(self):
        backend = _make_backend([_stop("Hello world")])
        result = backend.query("hi", "")
        assert result.response == "Hello world"

    def test_elapsed_is_non_negative(self):
        backend = _make_backend([_stop("ok")])
        result = backend.query("hi", "")
        assert result.elapsed >= 0.0

    def test_not_interrupted_on_normal_run(self):
        backend = _make_backend([_stop("ok")])
        result = backend.query("hi", "")
        assert result.interrupted is False

    def test_strips_markdown_before_returning(self):
        backend = _make_backend([_stop("**Bold** and `code`")])
        result = backend.query("hi", "")
        assert "**" not in result.response
        assert "`" not in result.response
        assert "Bold" in result.response

    def test_empty_response_returns_no_response_string(self):
        backend = _make_backend([_stop("")])
        result = backend.query("hi", "")
        assert result.response  # some i18n fallback string, not empty


# ── session management ────────────────────────────────────────────────────────


class TestSessionManagement:
    def test_session_expired_initially(self):
        backend = _make_backend([_stop("hi")])
        assert backend.session_expired() is True

    def test_new_session_true_on_first_call(self):
        backend = _make_backend([_stop("hi")])
        result = backend.query("hi", "")
        assert result.new_session is True

    def test_session_not_expired_after_query(self):
        backend = _make_backend([_stop("hi")])
        backend.query("hi", "")
        assert backend.session_expired() is False

    def test_new_session_false_on_second_call(self):
        backend = _make_backend([_stop("first"), _stop("second")])
        backend.query("turn1", "")
        result = backend.query("turn2", "")
        assert result.new_session is False

    def test_reset_session_clears_state(self):
        backend = _make_backend([_stop("hi")])
        backend.query("hi", "")
        assert not backend.session_expired()
        backend.reset_session()
        assert backend.session_expired()

    def test_session_expired_after_idle_timeout(self):
        backend = _make_backend([_stop("hi")])
        backend.query("hi", "")
        backend._last_interaction = time.time() - config.SESSION_IDLE_TIMEOUT - 1
        assert backend.session_expired() is True

    def test_new_session_after_reset_clears_history(self):
        backend = _make_backend([_stop("first"), _stop("second")])
        backend.query("turn1", "")
        assert len(backend._loop._messages) > 0
        backend.reset_session()
        assert backend._loop._messages == []


# ── multi-turn history ────────────────────────────────────────────────────────


class TestMultiTurnHistory:
    def test_history_grows_across_turns(self):
        backend = _make_backend([_stop("A"), _stop("B")])
        backend.query("turn1", "")
        msgs_after_1 = len(backend._loop._messages)
        backend.query("turn2", "")
        msgs_after_2 = len(backend._loop._messages)
        assert msgs_after_2 > msgs_after_1

    def test_system_prompt_not_stored_in_history(self):
        backend = _make_backend([_stop("ok")])
        backend.query("hi", "sys prompt here")
        roles = [m.role for m in backend._loop._messages]
        assert "system" not in roles

    def test_tool_results_kept_in_history(self):
        backend = _make_backend(
            [_tool_resp("1", "echo"), _stop("done")],
            tools={"echo": "result"},
        )
        backend.query("use tool", "")
        roles = [m.role for m in backend._loop._messages]
        assert "tool" in roles


# ── interrupt ─────────────────────────────────────────────────────────────────


class TestInterrupt:
    def test_interrupt_during_tool_returns_interrupted_result(self):
        """Tool calls backend.interrupt(); loop detects it on next check."""
        backend_ref: list[NativeBackend] = []

        provider = MockProvider([_tool_resp("1", "flagtool")])
        registry = ToolRegistry()

        def flagging_tool(_args):
            backend_ref[0].interrupt()
            return "ran"

        registry.register(ToolDef(name="flagtool", description="", parameters={}), flagging_tool)
        bus = ConversationBus()
        loop = AgentLoop(provider=provider, registry=registry, bus=bus)
        backend = NativeBackend(loop=loop)
        backend_ref.append(backend)

        result = backend.query("trigger interrupt", "")
        assert result.interrupted is True
        assert result.response == ""

    def test_interrupt_does_not_persist_to_next_query(self):
        """After an interrupted turn, the next query clears the interrupt flag."""
        backend_ref: list[NativeBackend] = []

        # First call: tool interrupts; second call: clean stop
        provider = MockProvider([_tool_resp("1", "flagtool"), _stop("clean")])
        registry = ToolRegistry()

        call_count = [0]

        def flagging_tool(_args):
            call_count[0] += 1
            if call_count[0] == 1:
                backend_ref[0].interrupt()
            return "ran"

        registry.register(ToolDef(name="flagtool", description="", parameters={}), flagging_tool)
        bus = ConversationBus()
        loop = AgentLoop(provider=provider, registry=registry, bus=bus)
        backend = NativeBackend(loop=loop)
        backend_ref.append(backend)

        first = backend.query("interrupt me", "")
        assert first.interrupted is True

        second = backend.query("clean turn", "")
        assert second.interrupted is False
        assert second.response == "clean"


# ── system prompt injection ───────────────────────────────────────────────────


class TestSystemPromptInjection:
    def test_system_prompt_injected_on_new_session(self):
        """Messages sent to provider on a new session start with system."""
        captured: list = []

        class CapturingProvider:
            def send(self, messages, tools, ctx=None):
                captured.extend(messages)
                return Response(content="ok", stop_reason="stop")

        registry = ToolRegistry()
        bus = ConversationBus()
        loop = AgentLoop(provider=CapturingProvider(), registry=registry, bus=bus)
        backend = NativeBackend(loop=loop)

        backend.query("hi", "you are a helpful assistant")
        assert captured[0].role == "system"
        assert "helpful assistant" in captured[0].content

    def test_obsidian_context_in_system_on_new_session(self):
        captured: list = []

        class CapturingProvider:
            def send(self, messages, tools, ctx=None):
                captured.extend(messages)
                return Response(content="ok", stop_reason="stop")

        registry = ToolRegistry()
        bus = ConversationBus()
        loop = AgentLoop(provider=CapturingProvider(), registry=registry, bus=bus)
        backend = NativeBackend(loop=loop)

        backend.query("hi", "sys", "memory context here")
        assert "memory context here" in captured[0].content

    def test_obsidian_context_absent_on_second_turn(self):
        captured_turns: list[list] = []

        class CapturingProvider:
            def send(self, messages, tools, ctx=None):
                captured_turns.append(list(messages))
                return Response(content="ok", stop_reason="stop")

        registry = ToolRegistry()
        bus = ConversationBus()
        loop = AgentLoop(provider=CapturingProvider(), registry=registry, bus=bus)
        backend = NativeBackend(loop=loop)

        backend.query("turn1", "sys", "obsidian memory")
        backend.query("turn2", "sys", "obsidian memory")

        # Turn 1: system message contains obsidian
        assert "obsidian memory" in captured_turns[0][0].content
        # Turn 2: system message must NOT contain obsidian
        assert "obsidian memory" not in captured_turns[1][0].content


# ── LLMBackend protocol compliance ───────────────────────────────────────────


class TestProtocolCompliance:
    def test_satisfies_llm_backend_protocol(self):
        backend = _make_backend([_stop("ok")])
        assert isinstance(backend, LLMBackend)


# ── filler loop ───────────────────────────────────────────────────────────────


class TestFillerLoop:
    def test_filler_called_during_query(self, monkeypatch):
        """speak_filler is invoked while the query runs."""
        monkeypatch.setattr(config, "FILLER_DELAY_SEC", 0.05)
        filler_calls: list[str] = []

        # MockProvider that introduces a small delay
        class SlowProvider:
            def send(self, messages, tools, ctx=None):
                time.sleep(0.15)
                return Response(content="ok", stop_reason="stop")

        registry = ToolRegistry()
        bus = ConversationBus()
        loop = AgentLoop(provider=SlowProvider(), registry=registry, bus=bus)
        backend = NativeBackend(loop=loop, speak_filler=filler_calls.append)

        backend.query("hi", "")
        assert len(filler_calls) >= 1

    def test_no_filler_when_speak_filler_is_none(self):
        backend = _make_backend([_stop("ok")], speak_filler=None)
        result = backend.query("hi", "")
        assert result.response == "ok"


# ── _build_system helper ──────────────────────────────────────────────────────


class TestBuildSystem:
    def test_empty_when_no_inputs(self):
        assert _build_system("", "") == ""

    def test_system_prompt_only(self):
        result = _build_system("be helpful", "")
        assert "be helpful" in result
        assert "Follow these instructions" in result

    def test_obsidian_only(self):
        result = _build_system("", "my notes")
        assert "my notes" in result
        assert "Restored context" in result

    def test_both_joined_with_separator(self):
        result = _build_system("sys", "obs")
        assert "---" in result
        assert "sys" in result
        assert "obs" in result


# ── factory ───────────────────────────────────────────────────────────────────


class TestBuildNativeBackend:
    def test_returns_native_backend(self):
        backend = build_native_backend()
        assert isinstance(backend, NativeBackend)

    def test_satisfies_llm_backend_protocol(self):
        backend = build_native_backend()
        assert isinstance(backend, LLMBackend)

    def test_all_tools_registered(self):
        backend = build_native_backend()
        names = {td.name for td in backend._loop._registry.definitions()}
        expected = {
            "bash",
            "read_file",
            "write_file",
            "edit_file",
            "search",
            "web_search",
            "web_fetch",
            "remember",
            "recall",
        }
        assert expected <= names

    def test_session_expired_initially(self):
        backend = build_native_backend()
        assert backend.session_expired() is True
