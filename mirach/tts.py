"""Text-to-speech using Piper with streaming, serialization, and filler pre-baking.

Three improvements over a naive Piper wrapper:
  * **Streaming**: audio chunks are fed to a sounddevice.OutputStream as Piper
    emits them, so playback starts before synthesis finishes.
  * **Serialized**: only one speak() is active at a time. Concurrent calls queue
    behind a lock, preventing filler phrases from overlapping with the answer.
  * **Pre-baked fillers**: short fixed phrases used during long LLM calls are
    synthesized once at startup and cached as WAV files for near-zero-latency playback.

interrupt() aborts the current OutputStream from any thread without holding
the playback queue lock.
"""

from __future__ import annotations

import contextlib
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
    """Piper TTS engine with streaming playback, persistent OutputStream, and interrupt.

    Opens the PortAudio OutputStream once at startup and reuses it across
    speak() calls via start()/stop() cycles, avoiding the creation of a new
    ALSA PCM device per turn. After an interrupt the stream is closed and
    lazily recreated on the next play call.
    """

    def __init__(self) -> None:
        self._voice: PiperVoice | None = None
        self._sample_rate: int = 22050
        self._stream: sd.OutputStream | None = None
        self._stream_lock = threading.RLock()  # reentrant — protects _stream assignment/abort
        self._playback_lock = threading.Lock()  # serializes speak() calls
        self._filler_cache: dict[str, str] = {}  # phrase → temp WAV path

    def load(self) -> None:
        """Load the Piper voice model from VOICE_PATH. Logs load time and sample rate."""
        t0 = time.time()
        self._voice = PiperVoice.load(str(config.VOICE_PATH))
        self._sample_rate = self._voice.config.sample_rate
        self._open_stream()
        log.info("Piper voice loaded (%.1fs, %d Hz)", time.time() - t0, self._sample_rate)

    def _open_stream(self) -> None:
        """Open (or reopen) the persistent OutputStream and start it."""
        with self._stream_lock:
            if self._stream is not None:
                with contextlib.suppress(Exception):
                    self._stream.close()
            self._stream = sd.OutputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
            )
            self._stream.start()

    def close(self) -> None:
        """Close the persistent OutputStream. Called once at daemon shutdown."""
        with self._stream_lock:
            if self._stream is not None:
                with contextlib.suppress(Exception):
                    self._stream.close()
                self._stream = None
                log.info("TTS OutputStream closed")

    # ── Public API ─────────────────────────────────────────────────────

    def speak(self, text: str) -> None:
        """Synthesize and play text. Blocks until playback finishes or is interrupted."""
        with self._playback_lock:
            assert self._voice is not None, "Piper not loaded"
            syn_config = SynthesisConfig(length_scale=config.VOICE_SPEED)
            chunks = (
                c.audio_int16_bytes for c in self._voice.synthesize(text, syn_config=syn_config)
            )
            self._play_stream(chunks, self._sample_rate)

    def speak_filler(self, phrase: str) -> None:
        """Play a filler phrase. Uses the pre-baked WAV if cached, otherwise synthesizes live."""
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
        """Stop current playback immediately. Safe to call from any thread.

        Closes the stream; it will be recreated lazily on the next call
        via _ensure_stream.
        """
        with self._stream_lock:
            if self._stream is not None:
                with contextlib.suppress(Exception):
                    self._stream.abort()
                self._stream.close()
                self._stream = None
                log.info("TTS interrupted (stream closed)")

    def prebake_fillers(self, phrases: list[str]) -> None:
        """Pre-synthesize and cache the given phrases as WAV files for fast playback."""
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

    # ── Internal playback ──────────────────────────────────────────────

    def _ensure_stream(self) -> sd.OutputStream:
        """Return the persistent OutputStream, recreating if closed.

        After a normal stop() the stream is still open (closed=False) and can
        be restarted with start(). Only after close() (e.g. from interrupt)
        does the stream need to be recreated.
        """
        if self._stream is None or self._stream.closed:
            self._open_stream()
        return self._stream

    def _play_stream(self, chunks: Iterable[bytes], samplerate: int) -> None:
        """Stream int16 PCM chunks through the persistent OutputStream."""
        t0 = time.time()
        with self._stream_lock:
            stream = self._ensure_stream()
            stream.start()

        first = True
        try:
            for raw in chunks:
                if not stream.active:
                    return  # interrupted
                stream.write(np.frombuffer(raw, dtype=np.int16))
                if first:
                    log.info("TTS first chunk (%.2fs)", time.time() - t0)
                    first = False
            stream.stop()
            log.info("TTS done (%.2fs total)", time.time() - t0)
        except sd.PortAudioError as e:
            log.error("TTS audio error: %s", e)

    def _play_wav(self, path: str) -> None:
        """Play a pre-rendered WAV file through the persistent OutputStream."""
        try:
            with wave.open(path, "rb") as wf:
                data = wf.readframes(wf.getnframes())
                sr = wf.getframerate()
            if sr != self._sample_rate:
                self._sample_rate = sr
                self._open_stream()
            self._play_stream([data], sr)
        except Exception as e:
            log.warning("WAV playback failed: %s", e)
