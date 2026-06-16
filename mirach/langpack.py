"""Language packs: map a daemon language code to its STT/TTS/locale settings.

A "language pack" bundles everything the daemon language governs:

* ``whisper_model`` — the faster-whisper model name (English-only is faster).
* ``whisper_lang``  — the ISO 639-1 code Whisper transcribes in.
* ``locale``        — ``MIRACH_LOCALE`` for spoken fillers and notifications.
* ``voice``         — the recommended Piper voice filename for the language.
* ``voice_url``     — Hugging Face URL for that voice's ``.onnx`` model.

This module is intentionally dependency-free (no sounddevice/whisper imports) so
both ``install.py`` and the future ``mirach lang`` CLI command can import it
cheaply. Keep it that way.
"""

from __future__ import annotations

DEFAULT_LANG = "en"

LANGUAGE_PACKS: dict[str, dict[str, str]] = {
    "es": {
        "whisper_model": "medium",  # multilingual model for Spanish
        "whisper_lang": "es",
        "locale": "es",
        "voice": "es_MX-ald-medium.onnx",
        "voice_url": (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
            "es/es_MX/ald/medium/es_MX-ald-medium.onnx"
        ),
    },
    "en": {
        "whisper_model": "medium.en",  # English-only model is faster
        "whisper_lang": "en",
        "locale": "en",
        "voice": "en_US-lessac-low.onnx",
        "voice_url": (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
            "en/en_US/lessac/low/en_US-lessac-low.onnx"
        ),
    },
}


def pack_for(lang_code: str) -> dict[str, str]:
    """Return a copy of the language pack for ``lang_code``, falling back to English.

    A copy is returned so callers can mutate it freely without corrupting the
    shared table.
    """
    return dict(LANGUAGE_PACKS.get(lang_code, LANGUAGE_PACKS[DEFAULT_LANG]))
