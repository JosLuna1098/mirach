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
MIC_NAME = _env("MIRACH_MIC", "")
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
VOICE_NAME = _env("MIRACH_VOICE", "en_US-lessac-low.onnx")
VOICE_PATH = VOICES_DIR / VOICE_NAME
VOICE_SPEED = _env_float("MIRACH_VOICE_SPEED", 1.2)

SESSION_IDLE_TIMEOUT = _env_float("MIRACH_SESSION_IDLE_TIMEOUT", 3600.0)  # 1 hour

# Voice-confirm: on a voice turn, Mirach speaks the confirmation question and waits
# for the user to press the hotkey and answer yes/no. If no answer is started within
# this many seconds, the pending tool call is auto-denied (fail-safe).
VOICE_CONFIRM_TIMEOUT = _env_float("MIRACH_VOICE_CONFIRM_TIMEOUT", 20.0)

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
# Default to qwen3:14b — the model validated for native tool-calling (protocol=auto).
NATIVE_MODEL = _env("MIRACH_NATIVE_MODEL", "qwen3:14b")
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
# Diagnostic: if set to a path, launch opencode serve with --print-logs and tee
# its stdout to that file (captures what opencode does during a hang). Empty = off.
OPENCODE_SERVE_LOG = _env("MIRACH_OPENCODE_SERVE_LOG", "")
# Path (or bare name) of the opencode binary — override when opencode is not on PATH.
OPENCODE_BIN = _env("MIRACH_OPENCODE_BIN", "opencode")
# Policy file is shared with the native backend; set MIRACH_NATIVE_POLICY to override.

# ── User feedback (beeps and fillers) ─────────────────────────────────
BEEP_START_WAV = os.path.join(_TMP, "mirach_beep_start.wav")
BEEP_PROCESS_WAV = os.path.join(_TMP, "mirach_beep_process.wav")
BEEP_SHUTDOWN_WAV = os.path.join(_TMP, "mirach_beep_shutdown.wav")
FILLER_DELAY_SEC = _env_float("MIRACH_FILLER_DELAY", 6.0)

# ── HTTP/SSE visibility server (Phase 3) ──────────────────────────────
# Set MIRACH_SERVER_ENABLED=0 to disable the local API server entirely.
SERVER_ENABLED = _env("MIRACH_SERVER_ENABLED", "1") == "1"
SERVER_HOST = _env("MIRACH_SERVER_HOST", "127.0.0.1")
SERVER_PORT = _env_int("MIRACH_SERVER_PORT", 7270)

# ── Context management (both backends) ────────────────────────────────
# Strategy: none (off) | sliding (drop oldest rounds) | summarize (LLM-summary prefix)
# Default "none" keeps current behaviour unchanged until explicitly opted in.
CONTEXT_STRATEGY = _env("MIRACH_CONTEXT_STRATEGY", "none")
# Conservative token budget — 32k lets long sessions run before triggering compaction.
CONTEXT_MAX_TOKENS = _env_int("MIRACH_CONTEXT_MAX_TOKENS", 32768)
