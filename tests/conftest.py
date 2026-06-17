"""Pytest config: put the repo root on sys.path so `import mirach` works."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from mirach.harness.events import ConversationBus  # noqa: E402
from mirach.llm_types import LLMResult  # noqa: E402


class FakeBackend:
    """A no-op LLMBackend used so `Assistant()` never spawns the real `opencode`.

    Implements the full LLMBackend protocol over a real ConversationBus, so any
    test that constructs `Assistant()` without injecting its own `llm=` gets a
    working bus (subscribe/publish) without launching an `opencode serve`
    subprocess. Dedicated backend tests (test_opencode_backend, test_native_backend)
    construct their backends directly and are unaffected by this.
    """

    def __init__(self, speak_filler=None) -> None:
        self._bus = ConversationBus()

    @property
    def bus(self) -> ConversationBus:
        return self._bus

    def query(self, text: str, system_prompt: str, obsidian_context: str = "") -> LLMResult:
        return LLMResult(response="", new_session=False, interrupted=False, elapsed=0.0)

    def interrupt(self) -> None: ...
    def session_expired(self) -> bool:
        return False

    def reset_session(self) -> None: ...
    def confirm(self, tool_call_id: str) -> None: ...
    def deny(self, tool_call_id: str) -> None: ...


@pytest.fixture(autouse=True)
def mock_opencode_backend(monkeypatch):
    """Replace the opencode_serve factory so no test spawns the real `opencode`.

    `Assistant.__init__` does a local `from mirach.harness.build import
    build_opencode_serve_backend`, so patching the attribute on that module
    intercepts every default backend construction in the suite.
    """
    import mirach.harness.build as build_mod

    monkeypatch.setattr(
        build_mod,
        "build_opencode_serve_backend",
        lambda speak_filler=None: FakeBackend(speak_filler=speak_filler),
    )
