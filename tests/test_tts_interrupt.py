"""Tests for PiperSpeaker interrupt semantics.

These exercise the abort flag without touching real audio hardware or a loaded
voice model — the goal is to prove that interrupt() reliably stops in-flight
playback and prevents a filler from reopening the stream afterwards.
"""

from mirach.tts import PiperSpeaker


class _FakeStream:
    """Minimal stand-in for a sounddevice.OutputStream."""

    def __init__(self) -> None:
        self.active = True
        self.closed = False
        self.writes: list[object] = []
        self.started = 0
        self.stopped = 0

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1

    def write(self, data) -> None:  # noqa: ANN001
        self.writes.append(data)


def test_speak_early_returns_when_aborted():
    """speak() must bail before touching the (unloaded) voice when aborted."""
    sp = PiperSpeaker()  # no voice loaded
    sp.interrupt()  # sets the abort flag
    # Would raise AssertionError "Piper not loaded" if it proceeded.
    sp.speak("hola")
    sp.speak_filler("un momento")  # also must not raise


def test_play_stream_does_not_open_stream_when_aborted(monkeypatch):
    """After interrupt(), _play_stream must not iterate chunks or open a stream."""
    sp = PiperSpeaker()
    sp.interrupt()

    opened = False

    def _fail_ensure():
        nonlocal opened
        opened = True
        raise AssertionError("stream must not be (re)opened while aborted")

    monkeypatch.setattr(sp, "_ensure_stream", _fail_ensure)

    consumed = []

    def chunks():
        consumed.append(1)
        yield b"\x00\x00"

    sp._play_stream(chunks(), 22050)
    assert not opened
    assert consumed == []  # generator never iterated


def test_play_stream_stops_mid_playback_on_abort(monkeypatch):
    """An abort raised mid-stream stops further writes on the next iteration."""
    sp = PiperSpeaker()
    fake = _FakeStream()
    monkeypatch.setattr(sp, "_ensure_stream", lambda: fake)

    def chunks():
        yield b"\x01\x00"  # written
        sp.interrupt()  # user aborts after the first chunk
        yield b"\x02\x00"  # must NOT be written

    sp._play_stream(chunks(), 22050)
    assert len(fake.writes) == 1


def test_clear_interrupt_reenables_playback():
    """clear_interrupt() lifts the abort flag so the next turn can speak."""
    sp = PiperSpeaker()
    sp.interrupt()
    assert sp._aborted.is_set()
    sp.clear_interrupt()
    assert not sp._aborted.is_set()
