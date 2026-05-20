# How to add a new locale

## Add strings to i18n.py

Open `~/mirach/mirach/i18n.py` and add a new entry to both `STRINGS` and `FILLERS`:

```python
STRINGS = {
    # ... existing locales ...
    "fr": {
        "recording_start_title": "🎤 Écoute...",
        "recording_start_body": "Appuyez sur {hotkey} pour terminer",
        "processing_title": "🤖 Traitement...",
        "processing_body": "Transcription",
        "you_said": "🗣 Vous avez dit:",
        "assistant": "🤖 Assistant",
        "daemon_ready_title": "🤖 Assistant prêt",
        "daemon_ready_body": "Daemon actif — {hotkey} pour parler",
        "daemon_not_running": "Le daemon ne fonctionne pas. Lancez-le avec: systemctl --user start mirach",
        "nothing_recorded": "Rien n'a été enregistré.",
        "didnt_hear": "Je ne vous ai pas bien entendu.",
        "didnt_understand": "Je n'ai pas compris, réessayez.",
        "error_occurred": "Une erreur s'est produite, réessayez.",
        "timeout_error": "Cela a pris trop de temps. Réessayez.",
        "generic_error": "Il y a eu une erreur. Réessayez.",
        "no_response": "Pas de réponse. Réessayez.",
        "still_working": "Je travaille encore dessus...",
        "complex_query": "Cela prend un peu plus de temps, je traite encore.",
        "process_failed": "Quelque chose a échoué. Réessayez.",
        "conversation_shown": "Conversation ouverte dans votre navigateur.",
        "no_conversation": "Aucune conversation enregistrée.",
    },
}

FILLERS = {
    # ... existing locales ...
    "fr": ["Un moment.", "Je vérifie.", "Hmm.", "Attendez."],
}
```

All keys from the English dict must be present. Missing keys fall back to English silently.

## Add trigger phrases

If you want built-in triggers (like "show conversation") in your new locale, add them to `BUILTIN_TRIGGERS` in `assistant.py`:

```python
BUILTIN_TRIGGERS: dict[str, tuple[str, str]] = {
    # ... existing triggers ...
    # French
    "montre la conversation": ("conversation_shown", "conversation"),
    "voir la conversation": ("conversation_shown", "conversation"),
}
```

## Set the locale

```ini
[Service]
Environment=MIRACH_LOCALE=fr
```

Then restart:

```bash
systemctl --user restart mirach
```
