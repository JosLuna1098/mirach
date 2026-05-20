"""Mirach — local-first voice assistant daemon.

Pipeline: Whisper STT → OpenCode LLM → Piper TTS.
Controlled via a Unix socket triggered by a desktop hotkey.
"""

__version__ = "0.1.0"
