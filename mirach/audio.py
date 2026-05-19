"""Microphone recording. Thread-safe."""

from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd

from mirach import config
from mirach.logging_setup import log


class AudioRecorder:
    def __init__(self) -> None:
        self._frames: list[np.ndarray] = []
        self._frames_lock = threading.Lock()
        self._stream: sd.InputStream | None = None
        self._device_idx: int | None = None

    def detect_microphone(self) -> None:
        """Pick a mic matching MIC_NAME, otherwise fall back to system default."""
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            if config.MIC_NAME.lower() in d["name"].lower() and d["max_input_channels"] > 0:
                self._device_idx = i
                log.info("Microphone selected: %s (idx=%d)", d["name"], i)
                return
        log.warning("Microphone '%s' not found, using system default", config.MIC_NAME)

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        with self._frames_lock:
            self._frames.append(indata.copy())

    def start(self) -> None:
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
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._frames_lock:
            if not self._frames:
                return None
            audio = np.concatenate(self._frames, axis=0).flatten()
            self._frames.clear()
        return audio
