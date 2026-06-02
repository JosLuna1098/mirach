"""Centralized configuration driven by MIRACH_* environment variables.

All tunables have sensible defaults. Override by exporting env vars before
launching the daemon, or set them in the systemd service file.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = tempfile.gettempdir()


def _env(name: str, default: str) -> str:
    """Read a string env var, returning default if unset."""
    return os.environ.get(name, default)


def _env_float(name: str, default: float) -> float:
    """Read a float env var, returning default on parse error."""
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    """Read an integer env var, returning default on parse error."""
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# ── Paths ──────────────────────────────────────────────────────────────
# Default to the repo containing this file (config.py is at <repo>/mirach/config.py).
# Resolves correctly for `pip install -e .` no matter where the repo lives.
# Override with MIRACH_BASE_DIR if logs/voices/system_prompt belong elsewhere.
BASE_DIR = Path(_env("MIRACH_BASE_DIR", str(Path(__file__).resolve().parent.parent)))
VOICES_DIR = BASE_DIR / "voices"
LOGS_DIR = BASE_DIR / "logs"
CONVERSATIONS_DIR = LOGS_DIR / "conversations"
LOG_PATH = LOGS_DIR / "daemon.log"
SYSTEM_PROMPT_PATH = Path(_env("MIRACH_SYSTEM_PROMPT", str(BASE_DIR / "system_prompt.md")))
SOCKET_PATH = _env("MIRACH_SOCKET", os.path.join(_TMP, "mirach.sock"))
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "mirach"
SESSION_ID_PATH = CACHE_DIR / "session_id"

# ── Obsidian vault (persistent memory) ────────────────────────────────
OBSIDIAN_VAULT = Path(_env("MIRACH_OBSIDIAN_VAULT", str(Path.home() / "ObsidianVault")))
OBSIDIAN_CACHE_MAX_AGE = _env_float("MIRACH_OBSIDIAN_CACHE_MAX_AGE", 300.0)  # 5 min

# ── Audio capture ─────────────────────────────────────────────────────
MIC_NAME = _env("MIRACH_MIC", "fifine")
SAMPLE_RATE = _env_int("MIRACH_SAMPLE_RATE", 48000)
WHISPER_SR = 16000  # Whisper requires 16 kHz input
RMS_SILENCE_THRESHOLD = _env_float("MIRACH_RMS_SILENCE", 0.005)
MAX_RECORDING_SEC = _env_float("MIRACH_MAX_RECORDING_SEC", 60.0)  # Safety cap

# ── STT (Whisper) ─────────────────────────────────────────────────────
WHISPER_MODEL = _env("MIRACH_WHISPER_MODEL", "medium")
WHISPER_DEVICE = _env("MIRACH_WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE = _env("MIRACH_WHISPER_COMPUTE", "int8")
WHISPER_LANG = _env("MIRACH_WHISPER_LANG", "es")
WHISPER_BEAM_SIZE = _env_int("MIRACH_WHISPER_BEAM_SIZE", 3)  # 1-5 (lower = faster)

# ── TTS (Piper) ───────────────────────────────────────────────────────
VOICE_NAME = _env("MIRACH_VOICE", "daniela.onnx")
VOICE_PATH = VOICES_DIR / VOICE_NAME
VOICE_SPEED = _env_float("MIRACH_VOICE_SPEED", 1.2)

# ── LLM (OpenCode CLI) ────────────────────────────────────────────────
OPENCODE_MODEL = _env("MIRACH_OPENCODE_MODEL", "opencode/deepseek-v4-flash-free")
OPENCODE_TIMEOUT = _env_float("MIRACH_OPENCODE_TIMEOUT", 120.0)
OPENCODE_TIMEOUT_CODING = _env_float("MIRACH_OPENCODE_TIMEOUT_CODING", 300.0)  # 5 min
# Keywords used to detect coding-related queries for dynamic timeout extension.
CODING_KEYWORDS = [
    "script",
    "code",
    "programa",
    "funcion",
    "function",
    "clase",
    "class",
    "modulo",
    "module",
    "api",
    "bug",
    "debug",
    "compilar",
    "compile",
    "build",
    "test",
    "implementar",
    "implement",
    "algoritmo",
    "algorithm",
    "python",
    "javascript",
    "rust",
    "bash",
    "shell",
    "crear un",
    "crea un",
    "escribir un",
    "write a",
    "generar",
    "generate",
]
SESSION_IDLE_TIMEOUT = _env_float("MIRACH_SESSION_IDLE_TIMEOUT", 3600.0)  # 1 hour

# ── User feedback (beeps and fillers) ─────────────────────────────────
BEEP_START_WAV = os.path.join(_TMP, "mirach_beep_start.wav")
BEEP_PROCESS_WAV = os.path.join(_TMP, "mirach_beep_process.wav")
BEEP_SHUTDOWN_WAV = os.path.join(_TMP, "mirach_beep_shutdown.wav")
FILLER_DELAY_SEC = _env_float("MIRACH_FILLER_DELAY", 6.0)
