"""Tests for the Assistant turn queue + interrupt/stop arbitration (Phase 3).

All heavy components (audio, STT, TTS, backend) are injected as mocks, so the
FSM + deque logic runs deterministically with no hardware or subprocesses.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from mirach.assistant import MAX_QUEUE, Assistant, State
from mirach.harness.events import ConversationBus
from mirach.llm_types import LLMResult


class FakeBackend:
    """Controllable LLMBackend: query() can block on a gate and honour interrupt."""

    def __init__(self) -> None:
        self.bus = ConversationBus()
        self.calls: list[str] = []
        self.confirmed: list[str] = []
        self.denied: list[str] = []
        self._gate = threading.Event()
        self._gate.set()  # set = proceed immediately; clear = block in query()
        self._interrupt = threading.Event()

    def block(self) -> None:
        self._gate.clear()

    def release(self) -> None:
        self._gate.set()

    def query(self, text: str, system_prompt: str, obsidian_context: str = "") -> LLMResult:
        self.calls.append(text)
        self._interrupt.clear()
        while not self._gate.is_set():
            if self._interrupt.is_set():
                return LLMResult("", False, True, 0.0)
            time.sleep(0.01)
        if self._interrupt.is_set():
            return LLMResult("", False, True, 0.0)
        return LLMResult(f"reply-{text}", False, False, 0.0)

    def interrupt(self) -> None:
        self._interrupt.set()

    def session_expired(self) -> bool:
        return False

    def reset_session(self) -> None:
        pass

    def confirm(self, tool_call_id: str) -> None:
        self.confirmed.append(tool_call_id)

    def deny(self, tool_call_id: str) -> None:
        self.denied.append(tool_call_id)


def _wait_until(cond, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


@pytest.fixture
def asst(monkeypatch):
    """An Assistant with all I/O mocked and a FakeBackend."""
    monkeypatch.setattr("mirach.assistant.notify", MagicMock())
    fake = FakeBackend()
    a = Assistant(audio=MagicMock(), stt=MagicMock(), tts=MagicMock(), llm=fake)
    a._conv = MagicMock()
    a._obsidian = MagicMock(get_context=lambda: "")
    a._system_prompt = ""
    a._user_scripts = []
    a._fake = fake  # for the tests
    return a


# ── enqueue / FIFO drain ────────────────────────────────────────────────────


def test_enqueue_while_processing_drains_in_order(asst):
    fake = asst._fake
    fake.block()

    assert asst.submit_turn("A")["status"] == "queued"
    assert _wait_until(lambda: fake.calls == ["A"])  # A is processing (blocked)
    assert asst._state is State.PROCESSING

    assert asst.submit_turn("B") == {"status": "queued", "position": 1}
    assert asst.submit_turn("C") == {"status": "queued", "position": 2}
    assert list(asst._queue) == ["B", "C"]

    fake.release()
    assert _wait_until(lambda: fake.calls == ["A", "B", "C"])
    assert _wait_until(lambda: asst._state is State.IDLE)
    assert len(asst._queue) == 0


def test_submit_empty_text_rejected(asst):
    assert asst.submit_turn("   ")["status"] == "rejected"
    assert asst._fake.calls == []


def test_queue_full_rejects(asst):
    fake = asst._fake
    fake.block()
    asst.submit_turn("A")  # starts processing (blocked), not in the queue
    assert _wait_until(lambda: fake.calls == ["A"])

    for i in range(MAX_QUEUE):
        assert asst.submit_turn(f"q{i}")["status"] == "queued"
    assert asst.submit_turn("overflow") == {"status": "rejected", "reason": "queue_full"}
    assert len(asst._queue) == MAX_QUEUE


# ── interrupt (front insert) ────────────────────────────────────────────────


def test_interrupt_jumps_front_and_preserves_queue(asst):
    fake = asst._fake
    fake.block()
    asst.submit_turn("A")
    assert _wait_until(lambda: fake.calls == ["A"])
    asst.submit_turn("B")
    asst.submit_turn("C")
    assert list(asst._queue) == ["B", "C"]

    # Interrupt A and inject Y at the front, keeping B, C.
    assert asst.submit_turn("Y", interrupt=True)["status"] == "accepted"
    fake.release()

    assert _wait_until(lambda: fake.calls == ["A", "Y", "B", "C"])
    assert _wait_until(lambda: asst._state is State.IDLE)


def test_interrupt_clear_queue_drops_pending(asst):
    fake = asst._fake
    fake.block()
    asst.submit_turn("A")
    assert _wait_until(lambda: fake.calls == ["A"])
    asst.submit_turn("B")
    asst.submit_turn("C")

    asst.submit_turn("Y", interrupt=True, clear_queue=True)
    fake.release()

    assert _wait_until(lambda: fake.calls == ["A", "Y"])
    assert _wait_until(lambda: asst._state is State.IDLE)
    # B and C were dropped, never executed.
    assert "B" not in fake.calls and "C" not in fake.calls


# ── stop ────────────────────────────────────────────────────────────────────


def test_stop_cancels_current_and_clears_queue(asst):
    fake = asst._fake
    fake.block()
    asst.submit_turn("A")
    assert _wait_until(lambda: fake.calls == ["A"])
    asst.submit_turn("B")
    asst.submit_turn("C")

    asst.stop()

    assert _wait_until(lambda: asst._state is State.IDLE)
    assert len(asst._queue) == 0
    # Give any errant drain a moment; B/C must never run.
    time.sleep(0.1)
    assert fake.calls == ["A"]


# ── voice interrupt preserves the text queue ────────────────────────────────


def test_voice_toggle_interrupt_preserves_text_queue(asst):
    fake = asst._fake
    fake.block()
    asst.submit_turn("A")
    assert _wait_until(lambda: fake.calls == ["A"])
    asst.submit_turn("B")
    asst.submit_turn("C")

    # Alt+Z while processing → interrupt + go to RECORDING (voice takes the slot).
    asst.toggle()

    assert _wait_until(lambda: asst._state is State.RECORDING)
    assert list(asst._queue) == ["B", "C"]  # queue NOT drained nor cleared
    # B/C did not start while we are recording.
    assert fake.calls == ["A"]


# ── confirm / deny / bus delegation ─────────────────────────────────────────


def test_confirm_deny_bus_delegate_to_backend(asst):
    asst.confirm("tc-1")
    asst.deny("tc-2")
    assert asst._fake.confirmed == ["tc-1"]
    assert asst._fake.denied == ["tc-2"]
    assert asst.bus is asst._fake.bus
