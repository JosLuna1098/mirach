"""Tests for the anti-aliased downsampler."""

import numpy as np

from mirach.stt import _downsample


def test_identity_when_rates_match():
    audio = np.random.randn(1000).astype(np.float32)
    out = _downsample(audio, 16000, 16000)
    np.testing.assert_array_equal(out, audio)


def test_decimation_length_48k_to_16k():
    audio = np.zeros(48000, dtype=np.float32)  # 1 second
    out = _downsample(audio, 48000, 16000)
    assert out.shape[0] == 16000


def test_returns_float32():
    audio = np.zeros(48000, dtype=np.float32)
    out = _downsample(audio, 48000, 16000)
    assert out.dtype == np.float32


def test_dc_signal_stays_dc():
    """A constant signal must remain constant after downsampling."""
    audio = np.full(48000, 0.5, dtype=np.float32)
    out = _downsample(audio, 48000, 16000)
    # Boxcar filter at the boundaries can dip; check the middle.
    mid = out[len(out) // 4 : 3 * len(out) // 4]
    assert np.allclose(mid, 0.5, atol=1e-5)
