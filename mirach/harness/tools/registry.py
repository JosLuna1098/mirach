"""ToolRegistry: register harness tools and dispatch execute calls."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mirach.harness.providers.base import ToolDef


@dataclass
class _RegisteredTool:
    definition: ToolDef
    fn: Callable[[dict[str, Any]], str]


class ToolRegistry:
    """Maps tool names to their ToolDef schema and execute function."""

    def __init__(self) -> None:
        self._tools: dict[str, _RegisteredTool] = {}

    def register(self, definition: ToolDef, fn: Callable[[dict[str, Any]], str]) -> None:
        self._tools[definition.name] = _RegisteredTool(definition=definition, fn=fn)

    def definitions(self) -> list[ToolDef]:
        """All registered tool schemas, to be sent to the provider."""
        return [t.definition for t in self._tools.values()]

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name!r}")
        return self._tools[name].fn(arguments)
