"""Tests for AgentLoop: inner tool-use loop, interrupt, event sequence, mobile-readiness."""

from __future__ import annotations

import threading

from mirach.harness.events import (
    ConversationBus,
    DoneEvent,
    ErrorEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from mirach.harness.loop import AgentLoop
from mirach.harness.providers.base import Response, ToolCall, ToolDef
from mirach.harness.providers.mock import MockProvider
from mirach.harness.tools.registry import ToolRegistry

# ── helpers ──────────────────────────────────────────────────────────────────


def _stop(text: str) -> Response:
    return Response(content=text, stop_reason="stop")


def _tool_call(tc_id: str, name: str, args: dict | None = None) -> Response:
    return Response(
        content="",
        stop_reason="tool_use",
        tool_calls=[ToolCall(id=tc_id, name=name, arguments=args or {})],
    )


def _make_loop(
    responses: list[Response],
    tools: dict[str, str] | None = None,
) -> tuple[AgentLoop, ConversationBus, list]:
    """
    Build a loop with MockProvider and optionally register tools.

    tools: {name: return_value} — each tool just returns its value.
    Returns (loop, bus, events_list).
    """
    provider = MockProvider(responses)
    registry = ToolRegistry()
    if tools:
        for name, retval in tools.items():
            captured = retval  # avoid late-binding in lambda

            def make_fn(rv):
                return lambda _args: rv

            registry.register(
                ToolDef(name=name, description="", parameters={}),
                make_fn(captured),
            )
    bus = ConversationBus()
    events: list = []
    bus.subscribe(events.append)
    loop = AgentLoop(provider=provider, registry=registry, bus=bus)
    return loop, bus, events


def _event_types(events: list) -> list[str]:
    return [type(e).__name__ for e in events]


# ── simple text turn ──────────────────────────────────────────────────────────


class TestSimpleTextTurn:
    def test_returns_final_text(self):
        loop, _, _ = _make_loop([_stop("Hello world")])
        assert loop.run("hi") == "Hello world"

    def test_publishes_text_delta_then_done(self):
        loop, _, events = _make_loop([_stop("Hello")])
        loop.run("hi")
        assert _event_types(events) == ["TextDeltaEvent", "DoneEvent"]
        assert events[0].delta == "Hello"
        assert events[1].content == "Hello"

    def test_no_text_delta_when_content_empty(self):
        # A stop response with empty content (valid edge case)
        loop, _, events = _make_loop([_stop("")])
        result = loop.run("hi")
        assert result == ""
        assert _event_types(events) == ["DoneEvent"]

    def test_turn_input_is_plain_text(self):
        """Mobile-readiness: a turn can be produced from text alone, no audio coupling."""
        loop, _, _ = _make_loop([_stop("ok")])
        result = loop.run("this is plain text, no STT required")
        assert result == "ok"


# ── tool call ────────────────────────────────────────────────────────────────


class TestToolCallExecution:
    def test_inner_loop_executes_tool_and_publishes_events(self):
        loop, _, events = _make_loop(
            [_tool_call("1", "greet"), _stop("Done")],
            tools={"greet": "hello from tool"},
        )
        result = loop.run("go")
        assert result == "Done"
        types = _event_types(events)
        assert types == ["ToolCallEvent", "ToolResultEvent", "TextDeltaEvent", "DoneEvent"]

    def test_tool_call_event_carries_name_and_args(self):
        loop, _, events = _make_loop(
            [_tool_call("1", "echo", {"text": "ping"}), _stop("ok")],
            tools={"echo": "pong"},
        )
        loop.run("go")
        tc_event = next(e for e in events if isinstance(e, ToolCallEvent))
        assert tc_event.id == "1"
        assert tc_event.name == "echo"
        assert tc_event.arguments == {"text": "ping"}

    def test_tool_result_event_carries_result(self):
        loop, _, events = _make_loop(
            [_tool_call("1", "calc"), _stop("ok")],
            tools={"calc": "42"},
        )
        loop.run("go")
        tr_event = next(e for e in events if isinstance(e, ToolResultEvent))
        assert tr_event.tool_call_id == "1"
        assert tr_event.result == "42"
        assert tr_event.error is False

    def test_tool_exception_is_caught_and_published_as_error_result(self):
        provider = MockProvider([_tool_call("1", "boom"), _stop("recovered")])
        registry = ToolRegistry()
        registry.register(
            ToolDef(name="boom", description="", parameters={}),
            lambda _: (_ for _ in ()).throw(RuntimeError("kaboom")),
        )
        bus = ConversationBus()
        events: list = []
        bus.subscribe(events.append)
        loop = AgentLoop(provider=provider, registry=registry, bus=bus)
        result = loop.run("go")
        assert result == "recovered"
        tr_event = next(e for e in events if isinstance(e, ToolResultEvent))
        assert tr_event.error is True
        assert "kaboom" in tr_event.result


# ── multi-turn tool use ───────────────────────────────────────────────────────


class TestMultiTurnToolUse:
    def test_two_sequential_tool_calls_before_stop(self):
        call_log: list[str] = []

        provider = MockProvider(
            [
                _tool_call("1", "step_a"),
                _tool_call("2", "step_b"),
                _stop("Finished"),
            ]
        )
        registry = ToolRegistry()
        for name in ("step_a", "step_b"):

            def make_fn(n):
                def fn(_args):
                    call_log.append(n)
                    return f"done_{n}"

                return fn

            registry.register(ToolDef(name=name, description="", parameters={}), make_fn(name))

        bus = ConversationBus()
        events: list = []
        bus.subscribe(events.append)
        loop = AgentLoop(provider=provider, registry=registry, bus=bus)
        result = loop.run("do both")

        assert result == "Finished"
        assert call_log == ["step_a", "step_b"]
        types = _event_types(events)
        assert types.count("ToolCallEvent") == 2
        assert types.count("ToolResultEvent") == 2
        assert types[-1] == "DoneEvent"


# ── interrupt ────────────────────────────────────────────────────────────────


class TestInterrupt:
    def test_interrupt_set_before_run_returns_empty(self):
        interrupt = threading.Event()
        interrupt.set()
        loop, _, events = _make_loop([])  # no responses needed
        result = loop.run("go", interrupt=interrupt)
        assert result == ""
        assert len(events) == 1
        assert isinstance(events[0], ErrorEvent)
        assert events[0].message == "interrupted"

    def test_interrupt_during_tool_execution_stops_loop(self):
        """Tool sets the interrupt; loop must not call provider again after that."""
        interrupt = threading.Event()

        provider = MockProvider(
            [
                _tool_call("1", "flagtool"),
                # No second response — if reached, MockProvider raises StopIteration.
            ]
        )
        registry = ToolRegistry()

        def flagging_fn(_args):
            interrupt.set()
            return "ran"

        registry.register(
            ToolDef(name="flagtool", description="", parameters={}),
            flagging_fn,
        )
        bus = ConversationBus()
        events: list = []
        bus.subscribe(events.append)
        loop = AgentLoop(provider=provider, registry=registry, bus=bus)
        result = loop.run("go", interrupt=interrupt)

        assert result == ""
        types = _event_types(events)
        # Tool ran and published its events; then loop detected interrupt and stopped.
        assert "ToolCallEvent" in types
        assert "ToolResultEvent" in types
        assert types[-1] == "ErrorEvent"

    def test_no_interrupt_runs_to_completion(self):
        interrupt = threading.Event()  # never set
        loop, _, events = _make_loop([_stop("done")])
        result = loop.run("hi", interrupt=interrupt)
        assert result == "done"
        assert _event_types(events) == ["TextDeltaEvent", "DoneEvent"]


# ── multiple subscribers (mobile-readiness) ───────────────────────────────────


class TestMultipleSubscribers:
    def test_all_subscribers_receive_all_events(self):
        """Mobile-readiness: bus supports multiple concurrent subscribers."""
        provider = MockProvider([_tool_call("1", "ping"), _stop("hi")])
        registry = ToolRegistry()
        registry.register(
            ToolDef(name="ping", description="", parameters={}),
            lambda _: "pong",
        )
        bus = ConversationBus()
        r_tts: list = []
        r_widget: list = []
        r_mobile: list = []
        bus.subscribe(r_tts.append)
        bus.subscribe(r_widget.append)
        bus.subscribe(r_mobile.append)

        loop = AgentLoop(provider=provider, registry=registry, bus=bus)
        loop.run("go")

        assert len(r_tts) == len(r_widget) == len(r_mobile)
        assert _event_types(r_tts) == _event_types(r_widget) == _event_types(r_mobile)

    def test_late_subscriber_can_replay_from_history(self):
        """Phase-3 resume: history is retained for reconnecting clients."""
        loop, bus, _ = _make_loop([_stop("hello")])
        loop.run("hi")

        # A client connecting *after* the turn can still read the full event history.
        late_events: list = []
        for event in bus.history():
            late_events.append(event)

        assert any(isinstance(e, DoneEvent) for e in late_events)
