"""Desktop notifications and beep generation/playback.

Wraps `notify-send` for asynchronous desktop notifications and generates
short WAV feedback tones (beeps) using numpy sine waves. Designed to be
swappable for a cross-platform implementation later.
"""

from __future__ import annotations

import contextlib
import logging
import os
import queue
import shutil
import subprocess
import threading
import wave

import numpy as np
import sounddevice as sd

from mirach import config

log = logging.getLogger("mirach")

# Single worker thread for notifications to avoid thread churn under burst conditions.
_notify_queue: queue.Queue[tuple[str, str, str]] = queue.Queue()
_notify_worker: threading.Thread | None = None

# Persistent OutputStream for beep playback (avoids creating a new ALSA PCM per beep).
_beep_stream: sd.OutputStream | None = None
_beep_stream_lock = threading.Lock()


def open_beep_stream(samplerate: int = 22050) -> None:
    """Open the persistent beep OutputStream. Called once at daemon startup."""
    global _beep_stream
    with _beep_stream_lock:
        if _beep_stream is not None:
            return
        _beep_stream = sd.OutputStream(
            samplerate=samplerate,
            channels=1,
            dtype="int16",
        )


def close_beep_stream() -> None:
    """Close the persistent beep OutputStream. Called once at daemon shutdown."""
    global _beep_stream
    with _beep_stream_lock:
        if _beep_stream is not None:
            with contextlib.suppress(Exception):
                _beep_stream.stop()
            _beep_stream.close()
            _beep_stream = None


def _notify_worker_loop() -> None:
    """Background worker that processes notifications from the queue."""
    while True:
        title, body, icon = _notify_queue.get()
        if title is None:  # Sentinel value to stop the worker
            break
        if shutil.which("notify-send"):
            subprocess.run(
                ["notify-send", "-t", "4000", "-i", icon, title, body],
                capture_output=True,
            )
        _notify_queue.task_done()


def _ensure_worker() -> None:
    """Start the notification worker thread if not already running."""
    global _notify_worker
    if _notify_worker is None or not _notify_worker.is_alive():
        _notify_worker = threading.Thread(target=_notify_worker_loop, daemon=True)
        _notify_worker.start()


def notify(title: str, body: str, icon: str = "dialog-information") -> None:
    """Send a desktop notification asynchronously via a shared worker thread.

    Silently skips if notify-send is unavailable.
    """
    if not shutil.which("notify-send"):
        log.debug("notify-send unavailable — skipping: %s", title)
        return
    _ensure_worker()
    _notify_queue.put((title, body, icon))


def _generate_beep_wav(
    path: str, freq_hz: int, dur_sec: float, volume: float = 0.3, sr: int = 22050
) -> None:
    """Write a sine-tone WAV file with 10 ms fade in/out to avoid audio clicks."""
    n = int(sr * dur_sec)
    t = np.linspace(0, dur_sec, n, endpoint=False)
    wave_data = volume * np.sin(2 * np.pi * freq_hz * t)
    fade = max(1, int(sr * 0.01))
    wave_data[:fade] *= np.linspace(0, 1, fade)
    wave_data[-fade:] *= np.linspace(1, 0, fade)
    pcm = (wave_data * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def _generate_descending_beep_wav(
    path: str,
    freqs: tuple[int, ...] = (660, 330),
    dur_per_tone: float = 0.12,
    gap: float = 0.04,
    volume: float = 0.3,
    sr: int = 22050,
) -> None:
    """Write a sequence of descending tones with short gaps. Used for the shutdown beep."""
    parts: list[np.ndarray] = []
    fade = max(1, int(sr * 0.01))
    gap_samples = np.zeros(int(sr * gap), dtype=np.float32)
    for freq in freqs:
        n = int(sr * dur_per_tone)
        t = np.linspace(0, dur_per_tone, n, endpoint=False)
        tone = volume * np.sin(2 * np.pi * freq * t)
        tone[:fade] *= np.linspace(0, 1, fade)
        tone[-fade:] *= np.linspace(1, 0, fade)
        parts.append(tone.astype(np.float32))
        parts.append(gap_samples)
    full = np.concatenate(parts[:-1])  # drop trailing gap
    pcm = (full * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def generate_beeps() -> None:
    """(Re)generate all feedback WAVs to the temp directory. Idempotent."""
    _generate_beep_wav(config.BEEP_START_WAV, freq_hz=1320, dur_sec=0.06)
    _generate_beep_wav(config.BEEP_PROCESS_WAV, freq_hz=660, dur_sec=0.08)
    _generate_descending_beep_wav(config.BEEP_SHUTDOWN_WAV)


def play_beep(path: str, blocking: bool = False) -> None:
    """Play a beep WAV via the persistent OutputStream.

    Non-blocking by default (returns immediately, audio plays out); blocking
    is used for the shutdown beep (calls stop() to wait for completion).
    """
    global _beep_stream
    if not path or not os.path.exists(path):
        return
    try:
        with wave.open(path, "rb") as wf:
            data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        with _beep_stream_lock:
            if _beep_stream is None:
                return
            _beep_stream.start()
            _beep_stream.write(data)
            if blocking:
                _beep_stream.stop()
    except Exception as e:
        log.warning("Beep playback failed: %s", e)
