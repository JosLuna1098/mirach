"""Tests for voice-confirm: a voice turn answers a tool confirmation by voice.

On a voice turn Mirach speaks the confirmation question and waits for the hotkey;
the first press records the spoken yes/no, the second submits it. A timeout or an
external answer (widget) resolves it instead. All I/O is mocked.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from mirach.assistant import Assistant
from mirach.harness.events import AwaitingConfirmationEvent, ConversationBus
from mirach.llm_types import LLMResult


class _FakeBackend:
    def __init__(self) -> None:
        self.bus = ConversationBus()
        self.confirmed: list[str] = []
        self.denied: list[str] = []

    def query(self, text: str, system_prompt: str, obsidian_context: str = "") -> LLMResult:
        return LLMResult("ok", False, False, 0.0)

    def interrupt(self) -> None:
        pass

    def session_expired(self) -> bool:
        return False

    def reset_session(self) -> None:
        pass

    def confirm(self, tool_call_id: str) -> None:
        self.confirmed.append(tool_call_id)

    def deny(self, tool_call_id: str) -> None:
        self.denied.append(tool_call_id)


def _wait_until(cond, timeout: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


def _event(tool_call_id="tc1", name="shell", arguments=None):
    return AwaitingConfirmationEvent(
        tool_call_id=tool_call_id, name=name, arguments=arguments or {}
    )


@pytest.fixture
def asst(monkeypatch):
    monkeypatch.setattr("mirach.assistant.notify", MagicMock())
    fake = _FakeBackend()
    a = Assistant(audio=MagicMock(), stt=MagicMock(), tts=MagicMock(), llm=fake)
    a._conv = MagicMock()
    a._fake = fake
    return a


# ── answer interpretation ────────────────────────────────────────────────────


@pytest.mark.parametrize("answer", ["sí", "Sí.", "claro que sí", "yes", "do it", "confirmo"])
def test_affirmative_yes(answer):
    assert Assistant._is_affirmative(answer)


@pytest.mark.parametrize("answer", ["no", "no lo hagas", "", "ni idea", "cancela"])
def test_affirmative_no(answer):
    assert not Assistant._is_affirmative(answer)


def test_describe_tool_prefers_salient_arg():
    assert Assistant._describe_tool(_event(name="shell", arguments={"command": "rm -rf x"})) == (
        "shell: rm -rf x"
    )


def test_describe_tool_falls_back_to_name():
    assert Assistant._describe_tool(_event(name="reboot", arguments={})) == "reboot"


# ── bus → spoken question ────────────────────────────────────────────────────


def test_voice_channel_speaks_question_and_arms(asst):
    asst._active_channel = "voice"
    asst.bus.publish(_event())
    # speak() runs after _voice_confirm is set, so waiting on it covers both.
    assert _wait_until(lambda: asst._tts.speak.called)
    assert asst._voice_confirm is not None
    assert asst._voice_confirm.tool_call_id == "tc1"
    asst._clear_voice_confirm()


def test_text_channel_does_not_voice_confirm(asst):
    asst._active_channel = "text"
    asst.bus.publish(_event())
    time.sleep(0.1)
    assert asst._voice_confirm is None
    asst._tts.speak.assert_not_called()


# ── hotkey answer flow ───────────────────────────────────────────────────────


def test_first_press_records_and_cancels_timeout(asst):
    asst._active_channel = "voice"
    asst._begin_voice_confirm(_event())
    pending = asst._voice_confirm
    assert pending is not None and not pending.recording

    asst.toggle()  # first press → record the answer
    assert pending.recording
    asst._audio.start.assert_called_once()
    assert pending.timer.finished.is_set()  # timeout cancelled
    asst._clear_voice_confirm()


def test_second_press_yes_confirms(asst):
    asst._active_channel = "voice"
    asst._stt.transcribe.return_value = "sí"
    asst._begin_voice_confirm(_event())
    asst.toggle()  # record
    asst.toggle()  # submit
    assert _wait_until(lambda: asst._fake.confirmed == ["tc1"])
    assert _wait_until(lambda: asst._voice_confirm is None)
    assert asst._fake.denied == []


def test_second_press_no_denies(asst):
    asst._active_channel = "voice"
    asst._stt.transcribe.return_value = "no"
    asst._begin_voice_confirm(_event())
    asst.toggle()
    asst.toggle()
    assert _wait_until(lambda: asst._fake.denied == ["tc1"])
    assert _wait_until(lambda: asst._voice_confirm is None)
    assert asst._fake.confirmed == []


# ── timeout + external answer ────────────────────────────────────────────────


def test_timeout_denies(asst):
    asst._active_channel = "voice"
    asst._begin_voice_confirm(_event())
    asst._voice_confirm_timeout("tc1")
    assert asst._fake.denied == ["tc1"]
    assert asst._voice_confirm is None


def test_external_answer_clears_pending(asst):
    asst._active_channel = "voice"
    asst._begin_voice_confirm(_event())
    pending = asst._voice_confirm
    asst.confirm("tc1")  # the widget answered first
    assert asst._voice_confirm is None
    assert asst._fake.confirmed == ["tc1"]
    assert pending.timer.finished.is_set()


def test_filler_suppressed_while_confirm_pending(asst):
    asst._active_channel = "voice"
    asst._begin_voice_confirm(_event())
    asst._on_filler("un momento")
    asst._tts.speak_filler.assert_not_called()
    asst._clear_voice_confirm()
