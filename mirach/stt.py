"""Speech-to-text using faster-whisper with performance optimizations.

Two refinements over a naive WhisperModel wrapper:
  * **Warmup**: a short silent buffer is fed to the model right after load()
    so the first real transcription doesn't pay the CUDA cold-start tax.
  * **Anti-aliased downsampling**: a polyphase filter (scipy if available,
    otherwise a boxcar low-pass) is applied before decimation, preserving
    consonants better than naive audio[::factor] decimation.
"""

from __future__ import annotations

import time
from math import gcd

import numpy as np
from faster_whisper import WhisperModel

from mirach import config
from mirach.logging_setup import log

# Optional: scipy provides higher-quality resampling. Falls back to boxcar filter.
try:
    from scipy.signal import resample_poly  # type: ignore

    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


def _downsample(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Convert audio from src_sr to dst_sr with anti-aliasing.

    Uses scipy's polyphase resampler when available for best quality.
    Falls back to a moving-average low-pass followed by integer decimation.
    Both approaches are adequate for speech recognition.
    """
    if src_sr == dst_sr:
        return audio.astype(np.float32)

    if _HAS_SCIPY:
        g = gcd(src_sr, dst_sr)
        return resample_poly(audio, dst_sr // g, src_sr // g).astype(np.float32)

    # Fallback: integer-factor decimation with a moving-average low-pass filter.
    factor = max(src_sr // dst_sr, 1)
    if factor == 1:
        return audio.astype(np.float32)
    kernel = np.ones(factor, dtype=np.float32) / factor
    filtered = np.convolve(audio.astype(np.float32), kernel, mode="same")
    return filtered[::factor]


class WhisperTranscriber:
    """Wraps faster-whisper with warmup, silence detection, and VAD filtering."""

    def __init__(self) -> None:
        self._model: WhisperModel | None = None

    def load(self) -> None:
        """Instantiate the WhisperModel. Logs load time and scipy availability."""
        t0 = time.time()
        self._model = WhisperModel(
            config.WHISPER_MODEL,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE,
        )
        log.info("Whisper loaded (%.1fs, scipy=%s)", time.time() - t0, _HAS_SCIPY)

    def warmup(self) -> None:
        """Run a throwaway transcription on silence to eliminate cold-start latency."""
        assert self._model is not None, "Whisper not loaded"
        t0 = time.time()
        silence = np.zeros(config.WHISPER_SR // 2, dtype=np.float32)  # 0.5 s of silence
        list(self._model.transcribe(silence, language=config.WHISPER_LANG))
        log.info("Whisper warmup (%.2fs)", time.time() - t0)

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe raw audio to text. Returns empty string for silence or no speech.

        Steps:
        1. Check RMS energy — discard if below silence threshold.
        2. Downsample to 16 kHz (Whisper's required rate).
        3. Run Whisper with VAD filter to skip non-speech segments.
        4. Filter out segments with high no-speech probability.
        """
        assert self._model is not None, "Whisper not loaded"
        t0 = time.time()

        # Reject silent audio early
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
        # Keep only segments where the model is confident speech is present
        valid = [s for s in segments if s.no_speech_prob < 0.6]
        text = " ".join(s.text for s in valid).strip()

        if not text:
            log.info("Empty transcription after VAD filter")
            return ""

        log.info("Transcribed (%.2fs): %s", time.time() - t0, text)
        return text
