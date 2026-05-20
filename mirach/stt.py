"""Speech-to-text using faster-whisper.

Adds two refinements over a naive wrapper:
  * **Warmup**: a short silent buffer is fed to the model right after load()
    so the first real transcription doesn't pay the cold-start tax.
  * **Anti-aliased downsampling**: a polyphase filter (scipy if available,
    otherwise a boxcar low-pass) is applied before decimation, preserving
    consonants better than `audio[::factor]` does.
"""

from __future__ import annotations

import time
from math import gcd

import numpy as np
from faster_whisper import WhisperModel

from mirach import config
from mirach.logging_setup import log

try:
    from scipy.signal import resample_poly  # type: ignore

    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


def _downsample(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Convert audio from src_sr to dst_sr with anti-aliasing.

    Uses scipy's polyphase resampler if available; otherwise applies a simple
    boxcar low-pass before decimation. Both are good enough for speech.
    """
    if src_sr == dst_sr:
        return audio.astype(np.float32)

    if _HAS_SCIPY:
        g = gcd(src_sr, dst_sr)
        return resample_poly(audio, dst_sr // g, src_sr // g).astype(np.float32)

    # Fallback: integer-factor decimation with a moving-average low-pass.
    factor = max(src_sr // dst_sr, 1)
    if factor == 1:
        return audio.astype(np.float32)
    kernel = np.ones(factor, dtype=np.float32) / factor
    filtered = np.convolve(audio.astype(np.float32), kernel, mode="same")
    return filtered[::factor]


class WhisperTranscriber:
    def __init__(self) -> None:
        self._model: WhisperModel | None = None

    def load(self) -> None:
        t0 = time.time()
        self._model = WhisperModel(
            config.WHISPER_MODEL,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE,
        )
        log.info("Whisper loaded (%.1fs, scipy=%s)", time.time() - t0, _HAS_SCIPY)

    def warmup(self) -> None:
        """Run a throwaway transcription so the first real one is fast."""
        assert self._model is not None, "Whisper not loaded"
        t0 = time.time()
        silence = np.zeros(config.WHISPER_SR // 2, dtype=np.float32)  # 0.5 s
        list(self._model.transcribe(silence, language=config.WHISPER_LANG))
        log.info("Whisper warmup (%.2fs)", time.time() - t0)

    def transcribe(self, audio: np.ndarray) -> str:
        assert self._model is not None, "Whisper not loaded"
        t0 = time.time()

        rms = float(np.sqrt(np.mean(audio**2)))
        if rms < config.RMS_SILENCE_THRESHOLD:
            log.info("Silent audio (RMS=%.4f) — discarded", rms)
            return ""

        audio_16k = _downsample(audio, config.SAMPLE_RATE, config.WHISPER_SR)

        segments, _ = self._model.transcribe(
            audio_16k,
            language=config.WHISPER_LANG,
            beam_size=config.WHISPER_BEAM_SIZE,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
        )
        valid = [s for s in segments if s.no_speech_prob < 0.6]
        text = " ".join(s.text for s in valid).strip()

        if not text:
            log.info("Empty transcription after VAD filter")
            return ""

        log.info("Transcribed (%.2fs): %s", time.time() - t0, text)
        return text
