"""Tests for ToolRegistry."""

from __future__ import annotations

import pytest

from mirach.harness.providers.base import ToolDef
from mirach.harness.tools.registry import ToolRegistry


def _echo_tool(args):
    return args.get("text", "")


def _add_tool(args):
    return str(int(args["a"]) + int(args["b"]))


class TestToolRegistry:
    def test_register_and_execute(self):
        registry = ToolRegistry()
        registry.register(ToolDef(name="echo", description="echo text", parameters={}), _echo_tool)
        assert registry.execute("echo", {"text": "hello"}) == "hello"

    def test_definitions_returns_registered_schemas(self):
        registry = ToolRegistry()
        registry.register(ToolDef(name="echo", description="d", parameters={}), _echo_tool)
        registry.register(ToolDef(name="add", description="d", parameters={}), _add_tool)
        names = {d.name for d in registry.definitions()}
        assert names == {"echo", "add"}

    def test_definitions_empty_when_nothing_registered(self):
        assert ToolRegistry().definitions() == []

    def test_unknown_tool_raises_key_error(self):
        registry = ToolRegistry()
        with pytest.raises(KeyError, match="unknown"):
            registry.execute("unknown", {})

    def test_register_overwrites_previous(self):
        registry = ToolRegistry()
        registry.register(ToolDef(name="t", description="v1", parameters={}), lambda _: "v1")
        registry.register(ToolDef(name="t", description="v2", parameters={}), lambda _: "v2")
        assert registry.execute("t", {}) == "v2"
        assert len(registry.definitions()) == 1

    def test_execute_passes_arguments(self):
        registry = ToolRegistry()
        registry.register(ToolDef(name="add", description="", parameters={}), _add_tool)
        assert registry.execute("add", {"a": "3", "b": "4"}) == "7"
