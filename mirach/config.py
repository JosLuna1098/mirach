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

SESSION_IDLE_TIMEOUT = _env_float("MIRACH_SESSION_IDLE_TIMEOUT", 3600.0)  # 1 hour

# ── Backend selection ─────────────────────────────────────────────────
# MIRACH_BACKEND=opencode_serve  (default) — delegate to opencode serve (HTTP+SSE)
# MIRACH_BACKEND=native                    — use the custom agentic harness (local LLMs)
BACKEND = _env("MIRACH_BACKEND", "opencode_serve")

# ── Native harness (MIRACH_BACKEND=native) ─────────────────────────────
# NOTE (Ollama tool-calling compat — see planning/harness/model-compat.md):
#   Not every model calls tools natively via Ollama. qwen2.5:7b returns an empty
#   stop instead of a tool_call → use MIRACH_NATIVE_TOOL_PROTOCOL=prompted with it.
#   qwen3:14b works with native tool-calling (use protocol=auto). When picking a
#   new model, verify native tool-calling before trusting protocol=auto.
NATIVE_BASE_URL = _env("MIRACH_NATIVE_BASE_URL", "http://localhost:11434")
NATIVE_MODEL = _env("MIRACH_NATIVE_MODEL", "gemma3:14b")
NATIVE_API_KEY = _env("MIRACH_NATIVE_API_KEY", "ollama")
NATIVE_NUM_CTX = _env_int("MIRACH_NATIVE_NUM_CTX", 32768)
NATIVE_TIMEOUT = _env_float("MIRACH_NATIVE_TIMEOUT", 120.0)
NATIVE_TEMPERATURE = _env_float("MIRACH_NATIVE_TEMPERATURE", 0.0)
# auto | native | prompted
NATIVE_TOOL_PROTOCOL = _env("MIRACH_NATIVE_TOOL_PROTOCOL", "auto")
# Path to user's policy.yaml; falls back to built-in restrictive defaults if absent.
NATIVE_POLICY_PATH = Path(_env("MIRACH_NATIVE_POLICY", str(BASE_DIR / "policy.yaml")))

# ── OpenCode serve backend (MIRACH_BACKEND=opencode_serve) ────────────
# opencode serve is launched as a supervised subprocess; port 0 = random free port.
OPENCODE_SERVE_HOST = _env("MIRACH_OPENCODE_SERVE_HOST", "127.0.0.1")
OPENCODE_SERVE_PORT = _env_int("MIRACH_OPENCODE_SERVE_PORT", 0)
OPENCODE_SERVE_CWD = _env("MIRACH_OPENCODE_SERVE_CWD", "")  # default: cwd at daemon start
OPENCODE_SERVE_STARTUP_TIMEOUT = _env_float("MIRACH_OPENCODE_SERVE_STARTUP_TIMEOUT", 15.0)
OPENCODE_SERVE_PROVIDER_ID = _env("MIRACH_OPENCODE_SERVE_PROVIDER_ID", "")
OPENCODE_SERVE_MODEL_ID = _env("MIRACH_OPENCODE_SERVE_MODEL_ID", "")
# Policy file is shared with the native backend; set MIRACH_NATIVE_POLICY to override.

# ── User feedback (beeps and fillers) ─────────────────────────────────
BEEP_START_WAV = os.path.join(_TMP, "mirach_beep_start.wav")
BEEP_PROCESS_WAV = os.path.join(_TMP, "mirach_beep_process.wav")
BEEP_SHUTDOWN_WAV = os.path.join(_TMP, "mirach_beep_shutdown.wav")
FILLER_DELAY_SEC = _env_float("MIRACH_FILLER_DELAY", 6.0)
