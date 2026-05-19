"""Lightweight i18n. Pick locale via MIRACH_LOCALE (default: en).

Add new locales by extending STRINGS and FILLERS.
"""

from __future__ import annotations

import os

DEFAULT_LOCALE = "en"
LOCALE = os.environ.get("MIRACH_LOCALE", DEFAULT_LOCALE)
HOTKEY = os.environ.get("MIRACH_HOTKEY", "Alt+Z")

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        # Notifications (visible)
        "recording_start_title": "🎤 Listening...",
        "recording_start_body": "Press {hotkey} to finish",
        "processing_title": "🤖 Processing...",
        "processing_body": "Transcribing",
        "you_said": "🗣 You said:",
        "assistant": "🤖 Assistant",
        "daemon_ready_title": "🤖 Assistant ready",
        "daemon_ready_body": "Daemon active — {hotkey} to talk",
        "daemon_not_running": (
            "The daemon is not running. Start it with: systemctl --user start mirach"
        ),
        # Spoken error fallbacks (TTS)
        "nothing_recorded": "Nothing was recorded.",
        "didnt_hear": "I didn't hear you well.",
        "didnt_understand": "I didn't understand, try again.",
        "error_occurred": "An error occurred, try again.",
        "timeout_error": "It took too long. Try again.",
        "generic_error": "There was an error. Try again.",
        "no_response": "No response. Try again.",
    },
    "es": {
        "recording_start_title": "🎤 Escuchando...",
        "recording_start_body": "Presiona {hotkey} para terminar",
        "processing_title": "🤖 Procesando...",
        "processing_body": "Transcribiendo",
        "you_said": "🗣 Tú dijiste:",
        "assistant": "🤖 Asistente",
        "daemon_ready_title": "🤖 Asistente listo",
        "daemon_ready_body": "Daemon activo — {hotkey} para hablar",
        "daemon_not_running": (
            "El daemon no está corriendo. Inícialo con: systemctl --user start mirach"
        ),
        "nothing_recorded": "No grabé nada.",
        "didnt_hear": "No te escuché bien.",
        "didnt_understand": "No entendí, intenta de nuevo.",
        "error_occurred": "Ocurrió un error, intenta de nuevo.",
        "timeout_error": "Tardó demasiado. Inténtalo de nuevo.",
        "generic_error": "Hubo un error. Inténtalo de nuevo.",
        "no_response": "No obtuve respuesta. Inténtalo de nuevo.",
    },
}

FILLERS: dict[str, list[str]] = {
    "en": ["One moment.", "Hold on.", "Let me see.", "Hmm.", "Just a sec."],
    "es": ["Un momento.", "Dame un segundo.", "A ver.", "Espera.", "Mmm."],
}


def t(key: str) -> str:
    """Translate a key. Falls back to English if missing in current locale."""
    raw = STRINGS.get(LOCALE, STRINGS[DEFAULT_LOCALE]).get(key, STRINGS[DEFAULT_LOCALE][key])
    return raw.replace("{hotkey}", HOTKEY)


def fillers() -> list[str]:
    """Return filler phrases for the current locale.

    Can be overridden entirely via MIRACH_FILLERS env var (pipe-separated).
    """
    override = os.environ.get("MIRACH_FILLERS")
    if override:
        return [s.strip() for s in override.split("|") if s.strip()]
    return FILLERS.get(LOCALE, FILLERS[DEFAULT_LOCALE])
