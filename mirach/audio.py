"""Microphone capture with thread-safe frame buffering.

Records raw PCM float32 audio from the system microphone using sounddevice.
Frames are collected via a callback and concatenated on stop().
"""

from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd

from mirach import config
from mirach.logging_setup import log


class AudioRecorder:
    """Thread-safe microphone recorder.

    Uses a callback-based InputStream to collect audio frames into a
    shared list protected by a lock. start()/stop() control the lifecycle.
    """

    def __init__(self) -> None:
        self._frames: list[np.ndarray] = []
        self._frames_lock = threading.Lock()
        self._stream: sd.InputStream | None = None
        self._device_idx: int | None = None

    def detect_microphone(self) -> None:
        """Select a microphone matching MIC_NAME, falling back to system default.

        Scans all input devices for one whose name contains the configured
        substring and has input channels. Logs a warning if no match is found.
        """
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            if config.MIC_NAME.lower() in d["name"].lower() and d["max_input_channels"] > 0:
                self._device_idx = i
                log.info("Microphone selected: %s (idx=%d)", d["name"], i)
                return
        log.warning("Microphone '%s' not found, using system default", config.MIC_NAME)

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        """sounddevice callback: append incoming audio frame to the buffer."""
        with self._frames_lock:
            self._frames.append(indata.copy())

    def start(self) -> None:
        """Open the microphone stream and begin recording."""
        with self._frames_lock:
            self._frames.clear()
        self._stream = sd.InputStream(
            samplerate=config.SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=self._callback,
            device=self._device_idx,
        )
        self._stream.start()
        log.info("Recording started")

    def stop(self) -> np.ndarray | None:
        """Stop the stream and return concatenated audio, or None if empty.

        Enforces a maximum recording duration to prevent unbounded memory growth.
        If the recording exceeds MAX_RECORDING_SEC, only the last portion is kept.
        """
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._frames_lock:
            if not self._frames:
                return None
            audio = np.concatenate(self._frames, axis=0).flatten()
            self._frames.clear()

        # Enforce max duration: truncate to the last N seconds if exceeded
        max_samples = int(config.SAMPLE_RATE * config.MAX_RECORDING_SEC)
        if len(audio) > max_samples:
            log.warning(
                "Recording exceeded %.1fs (max), truncating to last %.1fs",
                len(audio) / config.SAMPLE_RATE,
                config.MAX_RECORDING_SEC,
            )
            audio = audio[-max_samples:]

        return audio
