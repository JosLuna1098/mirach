"""Desktop notifications and beep generation/playback.

Wraps `notify-send` for asynchronous desktop notifications and generates
short WAV feedback tones (beeps) using numpy sine waves. Designed to be
swappable for a cross-platform implementation later.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import wave

import numpy as np
import sounddevice as sd

from mirach import config

log = logging.getLogger("mirach")


def notify(title: str, body: str, icon: str = "dialog-information") -> None:
    """Send a desktop notification asynchronously (non-blocking).

    Spawns a daemon thread to run notify-send so the main pipeline is not
    blocked by the subprocess. Silently skips if notify-send is unavailable.
    """
    if not shutil.which("notify-send"):
        log.debug("notify-send unavailable — skipping: %s", title)
        return

    def _send() -> None:
        subprocess.run(
            ["notify-send", "-t", "4000", "-i", icon, title, body],
            capture_output=True,
        )

    threading.Thread(target=_send, daemon=True).start()


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
    """Play a beep WAV via sounddevice. Non-blocking by default; blocking for shutdown."""
    if not path or not os.path.exists(path):
        return
    try:
        with wave.open(path, "rb") as wf:
            data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
            sr = wf.getframerate()
        sd.play(data, sr)
        if blocking:
            sd.wait()
    except Exception as e:
        log.warning("Beep playback failed: %s", e)
