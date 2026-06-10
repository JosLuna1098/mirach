"""AgentLoop: outer REPL + inner tool-use loop over a Provider and ToolRegistry."""

from __future__ import annotations

import threading

from mirach.harness.events import (
    ConversationBus,
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from mirach.harness.providers.base import Message, Provider, Response
from mirach.harness.tools.registry import ToolRegistry


class AgentLoop:
    """
    Drives the inner tool-use loop for a single text turn.

    Entry point is plain text — no coupling to audio. Local STT and the future
    mobile client are just edges that call run(text, ...).

    Interrupt semantics: checking happens at (1) the top of each while iteration
    (before calling the provider) and (2) before executing each tool. The
    currently-running tool always completes; the loop stops at the next checkpoint.
    """

    def __init__(
        self,
        provider: Provider,
        registry: ToolRegistry,
        bus: ConversationBus,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._bus = bus

    def run(
        self,
        turn: str,
        *,
        interrupt: threading.Event | None = None,
    ) -> str:
        """
        Execute one user turn, publishing events to the bus.

        Returns the final text answer, or "" if interrupted.
        """
        messages: list[Message] = [Message(role="user", content=turn)]

        while True:
            if interrupt and interrupt.is_set():
                self._bus.publish(ErrorEvent(message="interrupted"))
                return ""

            response: Response = self._provider.send(messages, self._registry.definitions())

            if response.content:
                self._bus.publish(TextDeltaEvent(delta=response.content))

            if response.stop_reason == "stop" or not response.tool_calls:
                self._bus.publish(DoneEvent(content=response.content))
                return response.content

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

                self._bus.publish(ToolCallEvent(id=tc.id, name=tc.name, arguments=tc.arguments))
                try:
                    result = self._registry.execute(tc.name, tc.arguments)
                    self._bus.publish(ToolResultEvent(tool_call_id=tc.id, result=result))
                except Exception as exc:
                    result = str(exc)
                    self._bus.publish(
                        ToolResultEvent(tool_call_id=tc.id, result=result, error=True)
                    )

                messages.append(Message(role="tool", tool_call_id=tc.id, content=result))
