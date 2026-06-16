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
    """Microphone recorder that only holds the ALSA device while recording.

    Uses PulseAudio via PortAudio (or PipeWire's PulseAudio compat layer)
    so the microphone can be shared with other apps (Discord, browser, etc).
    The InputStream is opened per recording turn and closed immediately after,
    preventing exclusive ALSA PCM lock.
    """

    def __init__(self) -> None:
        self._frames: list[np.ndarray] = []
        self._frames_lock = threading.Lock()
        self._stream: sd.InputStream | None = None
        self._device_spec: str | int | None = None
        self._recording = False

    def detect_microphone(self) -> None:
        """Select a microphone matching MIC_NAME via PulseAudio, falling back to default.

        Stores a PulseAudio source name (or device index as fallback)
        so the InputStream can be opened per-turn without holding it open.
        """
        # Prefer PulseAudio host API for device sharing
        api = sd.query_hostapis()
        pulse_api = next((a for a in api if "pulse" in a["name"].lower()), None)
        if pulse_api is not None:
            sd.default.hostapi = api.index(pulse_api)
            log.info("Using PulseAudio host API for device sharing")

        devices = sd.query_devices()
        if config.MIC_NAME:
            for _, d in enumerate(devices):
                if config.MIC_NAME.lower() in d["name"].lower() and d["max_input_channels"] > 0:
                    self._device_spec = d["name"]
                    log.info("Microphone selected: %s", d["name"])
                    return
            log.warning("Microphone '%s' not found, using system default", config.MIC_NAME)
        else:
            log.info("MIRACH_MIC not set — using system default input device")
        self._device_spec = None

    def open(self) -> None:
        """No-op: stream is opened per recording turn instead."""
        pass

    def close(self) -> None:
        """No-op: stream is closed per recording turn instead."""
        pass

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        """sounddevice callback: only accumulate frames when recording."""
        if self._recording:
            with self._frames_lock:
                self._frames.append(indata.copy())

    def start(self) -> None:
        """Open a fresh InputStream and begin recording."""
        with self._frames_lock:
            self._frames.clear()
        self._stream = sd.InputStream(
            samplerate=config.SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=self._callback,
            device=self._device_spec,
        )
        self._stream.start()
        self._recording = True
        log.info("Recording started")

    def stop(self) -> np.ndarray | None:
        """Stop recording, close the InputStream, and return concatenated audio."""
        self._recording = False
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
