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
class QueuedTurnEvent:
    """A text turn appended to the queue, not yet processing.

    Published at enqueue time so clients render a "pending" bubble immediately
    (and on resume show turns still waiting). The matching UserTurnEvent, emitted
    when the turn starts processing, settles it. QueueClearedEvent drops pending
    turns that were cancelled (stop / clear_queue) so resume shows no ghosts.
    """

    text: str
    type: Literal["queued"] = "queued"
    version: int = _V

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class QueueClearedEvent:
    """The pending queue was cleared (stop / clear_queue): drop pending bubbles."""

    type: Literal["queue_cleared"] = "queue_cleared"
    version: int = _V

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class UserTurnEvent:
    """A turn submitted by the user (voice transcript or typed text).

    Published at the start of every turn so all connected clients render the
    user's side of the shared conversation and replay it on resume.
    """

    text: str
    type: Literal["user_turn"] = "user_turn"
    version: int = _V

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


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
    QueuedTurnEvent
    | QueueClearedEvent
    | UserTurnEvent
    | TextDeltaEvent
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

    def attach(
        self, callback: Subscriber, since: int = 0
    ) -> tuple[list[Event], Callable[[], None]]:
        """Atomic catch-up + subscribe.

        Under a single lock: snapshots history[since:] and registers the
        callback as a subscriber.  No event published after this call is lost
        (no gap between replay and live stream).

        Returns (replay, unsubscribe).  The caller should process the replay
        list first, then read from whatever channel the callback feeds.
        """
        with self._lock:
            replay = list(self._history[since:])
            self._subscribers.append(callback)

        def unsubscribe() -> None:
            with self._lock, contextlib.suppress(ValueError):
                self._subscribers.remove(callback)

        return replay, unsubscribe
