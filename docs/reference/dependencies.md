# Dependencies Reference

## Runtime dependencies

| Package | Version | Purpose |
|---|---|---|
| `faster-whisper` | >=1.2, <2.0 | Speech-to-text via CTranslate2 (Whisper engine) |
| `piper-tts` | >=1.4, <2.0 | Local neural text-to-speech |
| `sounddevice` | >=0.5, <1.0 | Audio I/O — microphone capture and speaker playback |
| `numpy` | >=1.26, <3.0 | Numerical operations for audio processing |

## Optional dependencies

| Package | Version | Purpose |
|---|---|---|
| `scipy` | >=1.11 | High-quality polyphase resampling for Whisper downsampling. Falls back to boxcar filter if not installed. |

Install with: `pip install -e ".[quality]"`

## Development dependencies

| Package | Version | Purpose |
|---|---|---|
| `pytest` | >=8.0 | Test framework |
| `ruff` | >=0.6 | Linting and formatting |

Install with: `pip install -e ".[dev]"`

## System dependencies

| Package | Purpose | Required |
|---|---|---|
| PortAudio | Audio backend for sounddevice | Yes (pre-installed on most Linux desktops) |
| CUDA 12 drivers | GPU acceleration for Whisper | Yes for GPU mode |
| `nvidia-cublas-cu12` | CUDA 12 BLAS library (via pip) | Yes for GPU mode |
| `nvidia-cudnn-cu12` | CUDA 12 DNN library (via pip) | Yes for GPU mode |
| `notify-send` | Desktop notifications (libnotify) | Optional |
| `xdg-open` | Open URLs in default browser | Optional (for conversation viewer) |

## External dependencies (not in pyproject.toml)

| Component | Purpose | Installation |
|---|---|---|
| OpenCode CLI | LLM backend | Installed by `install.py` or manually |
| Piper voice models | TTS voice data | Downloaded by `install.py` from Hugging Face |
| Whisper model weights | STT model data | Downloaded automatically by faster-whisper on first use |

## CUDA library path

CTranslate2 (used by faster-whisper) requires CUDA 12 runtime libraries. These are installed via pip inside the venv's `site-packages`, not in the system library path. The `run_daemon.sh` script adds them to `LD_LIBRARY_PATH`:

```bash
export LD_LIBRARY_PATH="$SITE/nvidia/cublas/lib:$SITE/nvidia/cudnn/lib:${LD_LIBRARY_PATH:-}"
```

This is why you must use `run_daemon.sh` (or set `LD_LIBRARY_PATH` in your service file) instead of running `python -m mirach` directly for GPU mode.
