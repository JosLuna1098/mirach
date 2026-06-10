"""Provider Protocol and shared generic types for the harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass
class ToolDef:
    """Schema for a single harness tool, as presented to the LLM."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object describing the arguments


@dataclass
class ToolCall:
    """A tool invocation requested by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Message:
    """One message in the conversation history."""

    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str = ""  # populated when role == "tool"


@dataclass
class Response:
    """The provider's reply to a send() call."""

    content: str
    stop_reason: Literal["stop", "tool_use"]
    tool_calls: list[ToolCall] = field(default_factory=list)


class Provider(Protocol):
    """Pluggable LLM backend. Swap the brain by swapping the Provider."""

    def send(
        self,
        messages: list[Message],
        tools: list[ToolDef],
        ctx: dict[str, Any] | None = None,
    ) -> Response: ...
