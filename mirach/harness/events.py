"""ConversationBus and versioned, JSON-serializable event types."""

from __future__ import annotations

import contextlib
import dataclasses
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

_V = 1  # current event schema version


@dataclass
class TextDeltaEvent:
    delta: str
    type: Literal["text_delta"] = "text_delta"
    version: int = _V

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class ToolCallEvent:
    id: str
    name: str
    arguments: dict[str, Any]
    type: Literal["tool_call"] = "tool_call"
    version: int = _V

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class ToolResultEvent:
    tool_call_id: str
    result: str
    error: bool = False
    type: Literal["tool_result"] = "tool_result"
    version: int = _V

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class AwaitingConfirmationEvent:
    tool_call_id: str
    name: str
    arguments: dict[str, Any]
    type: Literal["awaiting_confirmation"] = "awaiting_confirmation"
    version: int = _V

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class DoneEvent:
    content: str
    type: Literal["done"] = "done"
    version: int = _V

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class ErrorEvent:
    message: str
    type: Literal["error"] = "error"
    version: int = _V

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class CostEvent:
    input_tokens: int
    output_tokens: int
    type: Literal["cost"] = "cost"
    version: int = _V

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


Event = (
    TextDeltaEvent
    | ToolCallEvent
    | ToolResultEvent
    | AwaitingConfirmationEvent
    | DoneEvent
    | ErrorEvent
    | CostEvent
)

Subscriber = Callable[[Event], None]


class ConversationBus:
    """
    Thread-safe publish/subscribe event bus.

    • Multiple concurrent subscribers are supported (mobile-readiness: widget + TTS
      + mobile client can all listen simultaneously).
    • History is retained so Phase 3 `resume` can replay recent events to reconnecting
      clients without losing context.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[Subscriber] = []
        self._history: list[Event] = []

    def subscribe(self, callback: Subscriber) -> Callable[[], None]:
        """Register a subscriber. Returns an idempotent unsubscribe callable."""
        with self._lock:
            self._subscribers.append(callback)

        def unsubscribe() -> None:
            with self._lock, contextlib.suppress(ValueError):
                self._subscribers.remove(callback)

        return unsubscribe

    def publish(self, event: Event) -> None:
        """Append to history and fan out to all current subscribers."""
        with self._lock:
            self._history.append(event)
            callbacks = list(self._subscribers)  # snapshot before releasing lock
        for cb in callbacks:
            cb(event)

    def history(self) -> list[Event]:
        """Return a copy of all events published since creation."""
        with self._lock:
            return list(self._history)
