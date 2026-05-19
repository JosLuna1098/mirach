"""Centralized configuration. Reads MIRACH_* env vars with sensible defaults.

Any value can be overridden by exporting the env var before launching the daemon.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = tempfile.gettempdir()


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# --- Paths ---
BASE_DIR = Path(_env("MIRACH_BASE_DIR", str(Path.home() / "mirach")))
VOICES_DIR = BASE_DIR / "voices"
LOGS_DIR = BASE_DIR / "logs"
CONVERSATIONS_DIR = LOGS_DIR / "conversations"
LOG_PATH = LOGS_DIR / "daemon.log"
SYSTEM_PROMPT_PATH = Path(_env("MIRACH_SYSTEM_PROMPT", str(BASE_DIR / "system_prompt.md")))
SOCKET_PATH = _env("MIRACH_SOCKET", os.path.join(_TMP, "mirach.sock"))

# --- Audio ---
MIC_NAME = _env("MIRACH_MIC", "fifine")
SAMPLE_RATE = _env_int("MIRACH_SAMPLE_RATE", 48000)
WHISPER_SR = 16000  # Whisper requires 16 kHz
RMS_SILENCE_THRESHOLD = _env_float("MIRACH_RMS_SILENCE", 0.005)

# --- STT ---
WHISPER_MODEL = _env("MIRACH_WHISPER_MODEL", "large-v3-turbo")
WHISPER_DEVICE = _env("MIRACH_WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE = _env("MIRACH_WHISPER_COMPUTE", "float16")
WHISPER_LANG = _env("MIRACH_WHISPER_LANG", "es")

# --- TTS ---
VOICE_NAME = _env("MIRACH_VOICE", "daniela.onnx")
VOICE_PATH = VOICES_DIR / VOICE_NAME
VOICE_SPEED = _env_float("MIRACH_VOICE_SPEED", 1.2)

# --- LLM (OpenCode CLI) ---
OPENCODE_MODEL = _env("MIRACH_OPENCODE_MODEL", "opencode/deepseek-v4-flash-free")
OPENCODE_TIMEOUT = _env_float("MIRACH_OPENCODE_TIMEOUT", 120.0)
SESSION_IDLE_TIMEOUT = _env_float("MIRACH_SESSION_IDLE_TIMEOUT", 120.0)

# --- User feedback ---
BEEP_START_WAV    = os.path.join(_TMP, "mirach_beep_start.wav")
BEEP_PROCESS_WAV  = os.path.join(_TMP, "mirach_beep_process.wav")
BEEP_SHUTDOWN_WAV = os.path.join(_TMP, "mirach_beep_shutdown.wav")
FILLER_DELAY_SEC = _env_float("MIRACH_FILLER_DELAY", 6.0)
