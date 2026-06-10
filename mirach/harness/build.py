"""Factories for harness backends (MIRACH_BACKEND=native / opencode_serve)."""

from __future__ import annotations

from collections.abc import Callable

from mirach import config
from mirach.harness.events import ConversationBus
from mirach.harness.loop import AgentLoop
from mirach.harness.native_backend import NativeBackend
from mirach.harness.policy.engine import PolicyEngine
from mirach.harness.providers.openai_compat import OpenAICompatProvider
from mirach.harness.tool_protocol import ToolProtocol
from mirach.harness.tools.files import (
    EDIT_FILE_DEF,
    READ_FILE_DEF,
    SEARCH_DEF,
    WRITE_FILE_DEF,
    edit_file,
    read_file,
    search,
    write_file,
)
from mirach.harness.tools.memory import RECALL_DEF, REMEMBER_DEF, make_recall, make_remember
from mirach.harness.tools.registry import ToolRegistry
from mirach.harness.tools.shell import BASH_DEF, bash
from mirach.harness.tools.web import WEB_FETCH_DEF, WEB_SEARCH_DEF, web_fetch, web_search


def build_native_backend(speak_filler: Callable[[str], None] | None = None) -> NativeBackend:
    """
    Assemble a NativeBackend from config.NATIVE_* variables.

    All components (provider, tools, policy, protocol) are wired here so
    assistant.py only needs a single import.
    """
    provider = OpenAICompatProvider(
        base_url=config.NATIVE_BASE_URL,
        model=config.NATIVE_MODEL,
        api_key=config.NATIVE_API_KEY,
        num_ctx=config.NATIVE_NUM_CTX,
        timeout=config.NATIVE_TIMEOUT,
        temperature=config.NATIVE_TEMPERATURE,
    )

    registry = ToolRegistry()
    registry.register(BASH_DEF, bash)
    registry.register(READ_FILE_DEF, read_file)
    registry.register(WRITE_FILE_DEF, write_file)
    registry.register(EDIT_FILE_DEF, edit_file)
    registry.register(SEARCH_DEF, search)
    registry.register(WEB_SEARCH_DEF, web_search)
    registry.register(WEB_FETCH_DEF, web_fetch)
    registry.register(REMEMBER_DEF, make_remember(config.OBSIDIAN_VAULT))
    registry.register(RECALL_DEF, make_recall(config.OBSIDIAN_VAULT))

    policy = PolicyEngine.load(config.NATIVE_POLICY_PATH)
    protocol = ToolProtocol(mode=config.NATIVE_TOOL_PROTOCOL)

    bus = ConversationBus()
    loop = AgentLoop(
        provider=provider,
        registry=registry,
        bus=bus,
        policy=policy,
        protocol=protocol,
    )

    return NativeBackend(loop=loop, speak_filler=speak_filler)


def build_opencode_serve_backend(
    speak_filler: Callable[[str], None] | None = None,
):
    """
    Assemble and start an OpenCodeServeBackend from MIRACH_OPENCODE_SERVE_* vars.

    Spawns `opencode serve` and waits for it to be ready before returning.
    The caller is responsible for calling backend.stop() at shutdown.
    """
    from mirach.harness.providers.opencode import OpenCodeServeBackend

    policy = PolicyEngine.load(config.NATIVE_POLICY_PATH)
    bus = ConversationBus()

    backend = OpenCodeServeBackend(
        policy=policy,
        bus=bus,
        host=config.OPENCODE_SERVE_HOST,
        port=config.OPENCODE_SERVE_PORT,
        provider_id=config.OPENCODE_SERVE_PROVIDER_ID,
        model_id=config.OPENCODE_SERVE_MODEL_ID,
        cwd=config.OPENCODE_SERVE_CWD,
        startup_timeout=config.OPENCODE_SERVE_STARTUP_TIMEOUT,
    )
    backend.start()
    return backend
