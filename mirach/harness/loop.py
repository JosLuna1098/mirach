"""AgentLoop: outer REPL + inner tool-use loop over a Provider and ToolRegistry."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from mirach.harness.events import (
    AwaitingConfirmationEvent,
    ConversationBus,
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from mirach.harness.providers.base import Message, Provider, Response, ToolCall
from mirach.harness.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from mirach.harness.context import ContextManager
    from mirach.harness.policy.engine import PolicyEngine
    from mirach.harness.tool_protocol import ToolProtocol


class AgentLoop:
    """
    Drives the inner tool-use loop for a single text turn.

    Entry point is plain text — no coupling to audio. Local STT and the future
    mobile client are just edges that call run(text, ...).

    Session history: self._messages accumulates the full conversation across
    multiple run() calls (user + assistant + tool exchanges). The system message
    is injected fresh on each run() via the system_prompt kwarg and is never
    stored in self._messages. Call reset() to start a new session.

    Policy + protocol are optional kwargs for backward compatibility with Phase 0
    tests; when omitted the loop behaves exactly as before (no policy checks,
    provider.send called directly).

    Interrupt semantics: checking happens at (1) the top of each while iteration
    (before calling the provider) and (2) before executing each tool. The
    currently-running tool always completes; the loop stops at the next checkpoint.

    Confirmation semantics: when the policy returns CONFIRM for a tool, the loop
    emits AwaitingConfirmationEvent and blocks until confirm(id) or deny(id) is
    called from another thread (e.g. the IPC server, the future widget).
    """

    def __init__(
        self,
        provider: Provider,
        registry: ToolRegistry,
        bus: ConversationBus,
        *,
        policy: PolicyEngine | None = None,
        protocol: ToolProtocol | None = None,
        context_manager: ContextManager | None = None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._bus = bus
        self._policy = policy
        self._protocol = protocol
        self._context_manager = context_manager

        # Conversation history — persists across run() calls; never includes system.
        self._messages: list[Message] = []

        # Per-call confirmation state — keyed by tool_call_id
        self._pending: dict[str, threading.Event] = {}
        self._confirmed: dict[str, bool] = {}
        self._confirm_lock = threading.Lock()

    # ── public API ────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Clear conversation history to start a new session."""
        self._messages = []

    def run(
        self,
        turn: str,
        *,
        interrupt: threading.Event | None = None,
        system_prompt: str = "",
    ) -> str:
        """
        Execute one user turn, publishing events to the bus.

        system_prompt is injected as a leading system message on every call but
        is never stored in self._messages — history only contains user/assistant/tool
        exchanges. Returns the final text answer, or "" if interrupted.
        """
        history_start = 1 if system_prompt else 0
        messages: list[Message] = []
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))
        messages.extend(self._messages)
        messages.append(Message(role="user", content=turn))

        tool_call_count = 0
        max_calls = self._policy.max_tool_calls_per_turn if self._policy else 25

        while True:
            if interrupt and interrupt.is_set():
                self._bus.publish(ErrorEvent(message="interrupted"))
                return ""

            # Get model response (via protocol if configured, else direct)
            response: Response = self._get_response(messages)

            if response.content:
                self._bus.publish(TextDeltaEvent(delta=response.content))

            if response.stop_reason == "stop" or not response.tool_calls:
                messages.append(Message(role="assistant", content=response.content))
                self._messages = messages[history_start:]
                if self._context_manager is not None:
                    self._messages = self._context_manager.compact_if_needed(
                        self._messages, self._provider
                    )
                self._bus.publish(DoneEvent(content=response.content))
                return response.content

            # max_tool_calls_per_turn guard
            tool_call_count += len(response.tool_calls)
            if tool_call_count > max_calls:
                self._bus.publish(
                    ErrorEvent(message=f"Runaway loop: exceeded {max_calls} tool calls in one turn")
                )
                return ""

            # Assistant turn with tool calls — append before executing.
            messages.append(
                Message(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            for tc in response.tool_calls:
                if interrupt and interrupt.is_set():
                    self._bus.publish(ErrorEvent(message="interrupted"))
                    return ""

                result = self._execute_tool(tc, interrupt)
                if result is None:
                    # interrupted or denied
                    return ""
                messages.append(Message(role="tool", tool_call_id=tc.id, content=result))

    def confirm(self, tool_call_id: str) -> None:
        """Approve a pending tool call from an external thread."""
        with self._confirm_lock:
            self._confirmed[tool_call_id] = True
            evt = self._pending.get(tool_call_id)
        if evt:
            evt.set()

    def deny(self, tool_call_id: str) -> None:
        """Reject a pending tool call from an external thread."""
        with self._confirm_lock:
            self._confirmed[tool_call_id] = False
            evt = self._pending.get(tool_call_id)
        if evt:
            evt.set()

    # ── private ───────────────────────────────────────────────────────────────

    def _get_response(self, messages: list[Message]) -> Response:
        tools = self._registry.definitions()
        if self._protocol is not None:
            return self._protocol.send_with_repair(self._provider, messages, tools)
        return self._provider.send(messages, tools)

    def _execute_tool(
        self,
        tc: ToolCall,
        interrupt: threading.Event | None,
    ) -> str | None:
        """
        Policy-check → optional confirmation → execute.
        Returns the result string, or None if interrupted/denied.
        """
        self._bus.publish(ToolCallEvent(id=tc.id, name=tc.name, arguments=tc.arguments))

        # Policy check
        if self._policy is not None:
            decision = self._policy.check(tc.name, tc.arguments)
            _Decision = _decision_enum()
            if decision == _Decision.DENY:
                result = f"[policy] Tool '{tc.name}' denied by policy."
                self._bus.publish(ToolResultEvent(tool_call_id=tc.id, result=result, error=True))
                return result
            if decision == _Decision.CONFIRM:
                confirmed = self._await_confirmation(tc, interrupt)
                if not confirmed:
                    result = f"[policy] Tool '{tc.name}' denied by user."
                    self._bus.publish(
                        ToolResultEvent(tool_call_id=tc.id, result=result, error=True)
                    )
                    return result

        # Execute
        try:
            result = self._registry.execute(tc.name, tc.arguments)
            self._bus.publish(ToolResultEvent(tool_call_id=tc.id, result=result))
        except Exception as exc:
            result = str(exc)
            self._bus.publish(ToolResultEvent(tool_call_id=tc.id, result=result, error=True))

        return result

    def _await_confirmation(
        self,
        tc: ToolCall,
        interrupt: threading.Event | None,
    ) -> bool:
        """Block until confirm()/deny() is called. Returns True if confirmed."""
        evt = threading.Event()
        with self._confirm_lock:
            self._pending[tc.id] = evt

        self._bus.publish(
            AwaitingConfirmationEvent(
                tool_call_id=tc.id,
                name=tc.name,
                arguments=tc.arguments,
            )
        )

        # Wait for response or interrupt
        while not evt.is_set():
            if interrupt and interrupt.is_set():
                with self._confirm_lock:
                    self._pending.pop(tc.id, None)
                return False
            evt.wait(timeout=0.1)

        with self._confirm_lock:
            self._pending.pop(tc.id, None)
            confirmed = self._confirmed.pop(tc.id, False)

        return confirmed


def _decision_enum():
    """Lazy import to avoid circular deps at module load time."""
    from mirach.harness.policy.engine import Decision

    return Decision
