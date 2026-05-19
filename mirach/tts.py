"""Text-to-speech using Piper.

Three improvements over a naive wrapper:
  * **Streaming**: audio chunks are fed to a sounddevice OutputStream as Piper
    emits them, so playback starts before synthesis finishes.
  * **Serialized**: only one playback is active at a time. Concurrent `speak()`
    calls queue behind each other, so a filler can't overlap with the answer.
  * **Pre-baked fillers**: short, fixed phrases used during long LLM calls are
    synthesized once at startup and cached as WAV files, so they play with
    near-zero overhead.

`interrupt()` aborts the current OutputStream from any thread without
holding the playback queue lock.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
import wave
from collections.abc import Iterable

import numpy as np
import sounddevice as sd
from piper import PiperVoice, SynthesisConfig

from mirach import config
from mirach.logging_setup import log

_TMP = tempfile.gettempdir()


class PiperSpeaker:
    def __init__(self) -> None:
        self._voice: PiperVoice | None = None
        self._sample_rate: int = 22050
        self._stream: sd.OutputStream | None = None
        self._stream_lock = threading.Lock()  # short critical sections around _stream
        self._playback_lock = threading.Lock()  # only one speak() runs at a time
        self._filler_cache: dict[str, str] = {}

    def load(self) -> None:
        t0 = time.time()
        self._voice = PiperVoice.load(str(config.VOICE_PATH))
        self._sample_rate = self._voice.config.sample_rate
        log.info("Piper voice loaded (%.1fs, %d Hz)", time.time() - t0, self._sample_rate)

    # --- Public API ---

    def speak(self, text: str) -> None:
        """Synthesize and play. Blocks until playback ends or is interrupted."""
        with self._playback_lock:
            assert self._voice is not None, "Piper not loaded"
            syn_config = SynthesisConfig(length_scale=config.VOICE_SPEED)
            chunks = (
                c.audio_int16_bytes for c in self._voice.synthesize(text, syn_config=syn_config)
            )
            self._play_stream(chunks, self._sample_rate)

    def speak_filler(self, phrase: str) -> None:
        """Play a filler. Uses the pre-baked WAV if available, otherwise synthesizes."""
        with self._playback_lock:
            cached = self._filler_cache.get(phrase)
            if cached and os.path.exists(cached):
                self._play_wav(cached)
            else:
                assert self._voice is not None, "Piper not loaded"
                syn_config = SynthesisConfig(length_scale=config.VOICE_SPEED)
                chunks = (
                    c.audio_int16_bytes
                    for c in self._voice.synthesize(phrase, syn_config=syn_config)
                )
                self._play_stream(chunks, self._sample_rate)

    def interrupt(self) -> None:
        """Stop current playback. Safe to call from any thread."""
        with self._stream_lock:
            if self._stream is not None and self._stream.active:
                self._stream.abort()
                log.info("TTS interrupted")
        # Also stop any sd.play() used for WAV fillers
        sd.stop()

    def prebake_fillers(self, phrases: list[str]) -> None:
        """Pre-synthesize and cache the given phrases as WAV files."""
        assert self._voice is not None, "Piper not loaded"
        t0 = time.time()
        syn_config = SynthesisConfig(length_scale=config.VOICE_SPEED)
        new_cache: dict[str, str] = {}
        for i, phrase in enumerate(phrases):
            path = os.path.join(_TMP, f"mirach_filler_{i}.wav")
            with wave.open(path, "wb") as wf:
                self._voice.synthesize_wav(phrase, wf, syn_config=syn_config)
            new_cache[phrase] = path
        self._filler_cache = new_cache
        log.info("Pre-baked %d fillers (%.2fs)", len(phrases), time.time() - t0)

    # --- Internal playback ---

    def _play_stream(self, chunks: Iterable[bytes], samplerate: int) -> None:
        """Stream raw int16 PCM chunks through a sounddevice OutputStream."""
        t0 = time.time()
        with self._stream_lock:
            self._stream = sd.OutputStream(samplerate=samplerate, channels=1, dtype="int16")
            self._stream.start()
            stream = self._stream

        first = True
        try:
            for raw in chunks:
                if not stream.active:
                    return
                stream.write(np.frombuffer(raw, dtype=np.int16))
                if first:
                    log.info("TTS first chunk (%.2fs)", time.time() - t0)
                    first = False
            stream.stop()
            log.info("TTS done (%.2fs total)", time.time() - t0)
        except sd.PortAudioError as e:
            log.error("TTS audio error: %s", e)
        finally:
            with self._stream_lock:
                self._stream = None

    def _play_wav(self, path: str) -> None:
        """Play a pre-rendered WAV file (cached fillers). Uses sd.play for simplicity."""
        try:
            with wave.open(path, "rb") as wf:
                data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
                sr = wf.getframerate()
            sd.play(data, sr)
            sd.wait()
        except Exception as e:
            log.warning("WAV playback failed: %s", e)
