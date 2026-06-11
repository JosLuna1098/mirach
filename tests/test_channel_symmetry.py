"""Tests for channel symmetry: a turn's answer leaves by the channel it entered.

Voice turns (PC mic / Alt+Z) are spoken on the PC; text turns (widget / mobile /
queue) stay silent and ride the bus to the widget instead. All heavy components
are mocked so the routing logic runs with no hardware.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from mirach import i18n
from mirach.assistant import Assistant, State
from mirach.harness.events import ConversationBus
from mirach.llm_types import LLMResult


class _FakeBackend:
    """Minimal LLMBackend whose query() returns a fixed response."""

    def __init__(self, response: str = "the answer") -> None:
        self.bus = ConversationBus()
        self._response = response
        self.calls: list[str] = []

    def query(self, text: str, system_prompt: str, obsidian_context: str = "") -> LLMResult:
        self.calls.append(text)
        return LLMResult(self._response, False, False, 0.0)

    def interrupt(self) -> None:
        pass

    def session_expired(self) -> bool:
        return False

    def reset_session(self) -> None:
        pass

    def confirm(self, tool_call_id: str) -> None:
        pass

    def deny(self, tool_call_id: str) -> None:
        pass


def _wait_until(cond, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


@pytest.fixture
def asst(monkeypatch):
    """An Assistant with all I/O mocked and a _FakeBackend."""
    monkeypatch.setattr("mirach.assistant.notify", MagicMock())
    fake = _FakeBackend()
    a = Assistant(audio=MagicMock(), stt=MagicMock(), tts=MagicMock(), llm=fake)
    a._conv = MagicMock()
    a._obsidian = MagicMock(get_context=lambda: "")
    a._system_prompt = ""
    a._user_scripts = []
    a._fake = fake
    return a


# ── answer routing ──────────────────────────────────────────────────────────


def test_voice_turn_speaks_answer(asst):
    """A voice turn speaks the backend answer on the PC."""
    asst._process(text="hi", channel="voice")
    asst._tts.speak.assert_called_once_with("the answer")


def test_text_turn_is_silent(asst):
    """A text turn must not speak on the PC — the answer rides the bus."""
    asst._process(text="hi", channel="text")
    asst._tts.speak.assert_not_called()


def test_text_turn_answer_not_double_published(asst):
    """The streamed answer is already on the bus, so _respond must not re-post it."""
    events = []
    asst.bus.subscribe(events.append)
    asst._process(text="hi", channel="text")
    assert not any(e.type == "done" for e in events)


def test_text_turn_canned_reply_surfaces_on_bus(asst):
    """An empty backend reply on text channel becomes a Done bubble, not speech."""
    asst._fake._response = ""  # forces the didnt_understand canned path
    events = []
    asst.bus.subscribe(events.append)
    asst._process(text="hi", channel="text")
    asst._tts.speak.assert_not_called()
    done = [e for e in events if e.type == "done"]
    assert any(e.content == i18n.t("didnt_understand") for e in done)


def test_voice_turn_canned_reply_is_spoken(asst):
    """The same empty reply on voice channel is spoken, not posted as a bubble."""
    asst._fake._response = ""
    events = []
    asst.bus.subscribe(events.append)
    asst._process(text="hi", channel="voice")
    asst._tts.speak.assert_called_once_with(i18n.t("didnt_understand"))
    assert not any(e.type == "done" for e in events)


# ── fillers ──────────────────────────────────────────────────────────────────


def test_filler_silent_on_text_channel(asst):
    asst._active_channel = "text"
    asst._on_filler("un momento")
    asst._tts.speak_filler.assert_not_called()


def test_filler_plays_on_voice_channel(asst):
    asst._active_channel = "voice"
    asst._on_filler("un momento")
    asst._tts.speak_filler.assert_called_once_with("un momento")


# ── queue drain is a text channel ────────────────────────────────────────────


def test_queue_drain_is_silent(asst):
    """Turns drained from the queue (widget / mobile) must not speak on the PC."""
    asst.submit_turn("hello")
    assert _wait_until(lambda: asst._fake.calls == ["hello"])
    assert _wait_until(lambda: asst._state is State.IDLE)
    asst._tts.speak.assert_not_called()
