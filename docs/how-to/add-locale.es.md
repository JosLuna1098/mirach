# Cómo añadir un nuevo idioma

Esta guía cubre el idioma del **daemon de escritorio** (`i18n.py`). La app de Android usa un pipeline ARB separado de `flutter gen-l10n` (`mobile/lib/l10n/app_*.arb`) — consulta [la nota del final](#idiomas-de-la-app-de-android).

## Añade textos a i18n.py

Abre `~/mirach/mirach/i18n.py` y añade una nueva entrada tanto a `STRINGS` como a `FILLERS`:

```python
STRINGS = {
    # ... idiomas existentes ...
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
    # ... idiomas existentes ...
    "fr": ["Un moment.", "Je vérifie.", "Hmm.", "Attendez."],
}
```

Todas las claves del diccionario en inglés deben estar presentes. Las claves que falten recurren al inglés en silencio.

## Añade frases de activación

Si quieres triggers integrados (como "show conversation") en tu nuevo idioma, añádelos a `BUILTIN_TRIGGERS` en `assistant.py`:

```python
BUILTIN_TRIGGERS: dict[str, tuple[str, str]] = {
    # ... triggers existentes ...
    # Francés
    "montre la conversation": ("conversation_shown", "conversation"),
    "voir la conversation": ("conversation_shown", "conversation"),
}
```

## Define el idioma

```bash
# mirach.env
MIRACH_LOCALE=fr
```

O vía systemd:

```ini
[Service]
Environment=MIRACH_LOCALE=fr
```

Luego reinicia:

```bash
systemctl --user restart mirach
# o: ./run_daemon.sh
```

## Idiomas de la app de Android

La app de Android **no** lee `i18n.py`. Sus textos viven en archivos ARB bajo `mobile/lib/l10n/`:

- `app_en.arb` — la plantilla (inglés)
- `app_es.arb` — español

Para añadir un idioma, crea `app_<código>.arb` con las mismas claves, luego regenera las clases de búsqueda en Dart:

```bash
cd mobile && /opt/flutter/bin/flutter gen-l10n
```

Los archivos generados están versionados en el repo. El idioma de la app se elige en el menú de opciones y se persiste bajo la clave `mirach_lang`; también controla el texto de las notificaciones del servicio en segundo plano vía `lookupAppLocalizations(Locale(code))`.
