"""Tests for AgentLoop with PolicyEngine: allow/deny/confirm gates, runaway guard."""

from __future__ import annotations

import threading
import time

from mirach.harness.events import (
    AwaitingConfirmationEvent,
    ConversationBus,
    ErrorEvent,
    ToolResultEvent,
)
from mirach.harness.loop import AgentLoop
from mirach.harness.policy.engine import PolicyEngine
from mirach.harness.policy.schema import Policy, PolicyDefaults, ShellPolicy
from mirach.harness.providers.base import Response, ToolCall, ToolDef
from mirach.harness.providers.mock import MockProvider
from mirach.harness.tools.registry import ToolRegistry

# ── helpers ───────────────────────────────────────────────────────────────────


def _stop(text: str = "done") -> Response:
    return Response(content=text, stop_reason="stop")


def _tool_resp(tc_id: str, name: str, args: dict | None = None) -> Response:
    return Response(
        content="",
        stop_reason="tool_use",
        tool_calls=[ToolCall(id=tc_id, name=name, arguments=args or {})],
    )


def _make_loop(
    responses: list[Response],
    tools: dict[str, str] | None = None,
    policy: PolicyEngine | None = None,
) -> tuple[AgentLoop, list]:
    provider = MockProvider(responses)
    registry = ToolRegistry()
    if tools:
        for name, retval in tools.items():
            def make_fn(rv):
                return lambda _args: rv
            registry.register(ToolDef(name=name, description="", parameters={}), make_fn(retval))
    bus = ConversationBus()
    events: list = []
    bus.subscribe(events.append)
    loop = AgentLoop(provider=provider, registry=registry, bus=bus, policy=policy)
    return loop, events


def _policy_with_shell(
    mode: str = "allowlist",
    allow: list[str] | None = None,
    confirm: list[str] | None = None,
    deny: list[str] | None = None,
) -> PolicyEngine:
    shell = ShellPolicy(
        mode=mode,
        allow=allow or [],
        confirm=confirm or [],
        deny=deny or [],
    )
    return PolicyEngine(Policy(defaults=PolicyDefaults(shell=shell)))


# ── policy ALLOW path ─────────────────────────────────────────────────────────


class TestPolicyAllow:
    def test_allowed_tool_executes_normally(self):
        """Tool not in any policy category → ALLOW (default)."""
        loop, events = _make_loop(
            [_tool_resp("1", "remember"), _stop("ok")],
            tools={"remember": "saved"},
            policy=PolicyEngine(),
        )
        result = loop.run("remember something")
        assert result == "ok"
        types = [type(e).__name__ for e in events]
        assert "ToolResultEvent" in types
        tr = next(e for e in events if isinstance(e, ToolResultEvent))
        assert tr.error is False
        assert tr.result == "saved"


# ── policy DENY path ──────────────────────────────────────────────────────────


class TestPolicyDeny:
    def test_denied_tool_returns_policy_error(self):
        """bash with denied command → ToolResultEvent with error=True, loop continues."""
        policy = _policy_with_shell(mode="allowlist", allow=[], confirm=[], deny=["rm"])
        loop, events = _make_loop(
            [_tool_resp("1", "bash", {"command": "rm -rf /"}), _stop("recovered")],
            tools={"bash": "should_not_run"},
            policy=policy,
        )
        result = loop.run("delete everything")
        assert result == "recovered"
        tr = next(e for e in events if isinstance(e, ToolResultEvent))
        assert tr.error is True
        assert "denied" in tr.result.lower()

    def test_denied_tool_does_not_execute_fn(self):
        """The tool function must NOT be called when policy denies."""
        executed: list[bool] = []

        policy = _policy_with_shell(mode="allowlist", allow=[], deny=["rm"])
        provider = MockProvider([_tool_resp("1", "bash", {"command": "rm /"}), _stop("done")])
        registry = ToolRegistry()
        registry.register(
            ToolDef(name="bash", description="", parameters={}),
            lambda _: executed.append(True) or "ran",
        )
        bus = ConversationBus()
        loop = AgentLoop(provider=provider, registry=registry, bus=bus, policy=policy)
        loop.run("go")
        assert executed == []


# ── policy CONFIRM path ───────────────────────────────────────────────────────


class TestPolicyConfirm:
    def test_confirm_emits_awaiting_event(self):
        policy = _policy_with_shell(mode="allowlist", allow=[], confirm=["rm"], deny=[])
        loop, events = _make_loop(
            [_tool_resp("1", "bash", {"command": "rm file.txt"}), _stop("done")],
            tools={"bash": "deleted"},
            policy=policy,
        )

        def auto_confirm():
            # Wait briefly for the awaiting event, then confirm
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if any(isinstance(e, AwaitingConfirmationEvent) for e in events):
                    loop.confirm("1")
                    return
                time.sleep(0.01)

        t = threading.Thread(target=auto_confirm, daemon=True)
        t.start()
        result = loop.run("delete file")
        t.join(timeout=3)

        assert result == "done"
        assert any(isinstance(e, AwaitingConfirmationEvent) for e in events)
        tr = next(e for e in events if isinstance(e, ToolResultEvent))
        assert tr.error is False
        assert tr.result == "deleted"

    def test_deny_confirmation_returns_policy_denied(self):
        policy = _policy_with_shell(mode="allowlist", allow=[], confirm=["rm"], deny=[])
        executed: list[bool] = []

        provider = MockProvider([_tool_resp("1", "bash", {"command": "rm file.txt"}), _stop("ok")])
        registry = ToolRegistry()
        registry.register(
            ToolDef(name="bash", description="", parameters={}),
            lambda _: executed.append(True) or "ran",
        )
        bus = ConversationBus()
        events: list = []
        bus.subscribe(events.append)
        loop = AgentLoop(provider=provider, registry=registry, bus=bus, policy=policy)

        def auto_deny():
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if any(isinstance(e, AwaitingConfirmationEvent) for e in events):
                    loop.deny("1")
                    return
                time.sleep(0.01)

        t = threading.Thread(target=auto_deny, daemon=True)
        t.start()
        loop.run("delete file")
        t.join(timeout=3)

        # Tool function was not called
        assert executed == []
        tr = next(e for e in events if isinstance(e, ToolResultEvent))
        assert tr.error is True
        assert "denied" in tr.result.lower()

    def test_confirm_awaiting_event_carries_tool_info(self):
        policy = _policy_with_shell(mode="allowlist", allow=[], confirm=["rm"], deny=[])
        loop, events = _make_loop(
            [_tool_resp("abc", "bash", {"command": "rm /tmp/x"}), _stop("ok")],
            tools={"bash": "done"},
            policy=policy,
        )

        def auto_confirm():
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                aw = next((e for e in events if isinstance(e, AwaitingConfirmationEvent)), None)
                if aw:
                    assert aw.tool_call_id == "abc"
                    assert aw.name == "bash"
                    assert aw.arguments["command"] == "rm /tmp/x"
                    loop.confirm("abc")
                    return
                time.sleep(0.01)

        t = threading.Thread(target=auto_confirm, daemon=True)
        t.start()
        loop.run("delete x")
        t.join(timeout=3)


# ── max_tool_calls_per_turn guard ─────────────────────────────────────────────


class TestMaxToolCallsGuard:
    def test_runaway_loop_is_cut(self):
        """Loop aborts after max_tool_calls_per_turn tool calls."""
        from mirach.harness.policy.schema import GuardsPolicy

        policy = PolicyEngine(Policy(guards=GuardsPolicy(max_tool_calls_per_turn=2)))

        # Provider keeps emitting tool calls, registry always returns "ok"
        responses = [_tool_resp(str(i), "remember") for i in range(10)] + [_stop("final")]
        provider = MockProvider(responses)
        registry = ToolRegistry()
        registry.register(
            ToolDef(name="remember", description="", parameters={}),
            lambda _: "ok",
        )
        bus = ConversationBus()
        events: list = []
        bus.subscribe(events.append)
        loop = AgentLoop(provider=provider, registry=registry, bus=bus, policy=policy)

        result = loop.run("loop forever")
        assert result == ""
        error_events = [e for e in events if isinstance(e, ErrorEvent)]
        assert any("Runaway" in e.message for e in error_events)

    def test_within_limit_completes_normally(self):
        from mirach.harness.policy.schema import GuardsPolicy

        policy = PolicyEngine(Policy(guards=GuardsPolicy(max_tool_calls_per_turn=5)))
        loop, events = _make_loop(
            [_tool_resp("1", "remember"), _tool_resp("2", "remember"), _stop("done")],
            tools={"remember": "ok"},
            policy=policy,
        )
        result = loop.run("do two things")
        assert result == "done"


# ── backward compatibility — no policy ───────────────────────────────────────


class TestNoPolicyBackwardCompat:
    def test_loop_without_policy_works_as_before(self):
        """Phase 0 tests: AgentLoop without policy arg runs unchanged."""
        provider = MockProvider([_tool_resp("1", "greet"), _stop("Hello")])
        registry = ToolRegistry()
        registry.register(
            ToolDef(name="greet", description="", parameters={}),
            lambda _: "hi",
        )
        bus = ConversationBus()
        loop = AgentLoop(provider=provider, registry=registry, bus=bus)
        result = loop.run("say hi")
        assert result == "Hello"
