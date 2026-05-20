# How-to Guides

Practical recipes for solving specific problems with Mirach.

## How to add a custom voice command (user script)

User scripts let you bypass the LLM and run shell commands directly when you say a trigger phrase.

### Create a script

Place a `.sh` or `.py` file in `~/mirach/user_scripts/` with metadata comments at the top:

```bash
#!/bin/bash
# triggers: focus mode, modo focus
# response: Focus mode activated.
# description: Enables focus mode by turning on nightlight and Do Not Disturb

omarchy-toggle-nightlight
notify-send "Focus mode" "Nightlight enabled, notifications muted"
```

### Metadata format

| Comment | Required | Description |
|---|---|---|
| `# triggers:` | Yes | Comma-separated phrases that trigger this script (matched case-insensitively) |
| `# response:` | Yes | Text spoken aloud after the script runs |
| `# description:` | No | Human-readable description (for your reference) |

### How it works

1. The daemon parses all scripts in `user_scripts/` at startup
2. When you speak, the transcribed text is checked against all trigger phrases
3. If a match is found, the script runs in the background and the response is spoken
4. No LLM call is made — this is instant

### Reload scripts

After adding or editing scripts, restart the daemon:

```bash
systemctl --user restart mirach
```

## How to change the Piper voice

### Download a new voice

Browse available voices at [rhasspy/piper-voices on Hugging Face](https://huggingface.co/rhasspy/piper-voices/tree/main).

Download the `.onnx` and `.onnx.json` files to `~/mirach/voices/`:

```bash
cd ~/mirach/voices
curl -L -o en_US-lessac-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
curl -L -o en_US-lessac-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

### Configure the voice

Set the `MIRACH_VOICE` environment variable in your systemd service:

```bash
systemctl --user edit mirach
```

Add:

```ini
[Service]
Environment=MIRACH_VOICE=en_US-lessac-medium.onnx
```

Then restart:

```bash
systemctl --user restart mirach
```

### Adjust voice speed

The `MIRACH_VOICE_SPEED` variable controls the `length_scale` parameter (>1 = slower, <1 = faster):

```ini
Environment=MIRACH_VOICE_SPEED=1.0
```

Default is `1.2`.

## How to change the Whisper model

### Available models

| Model | Size | VRAM | Speed | Notes |
|---|---|---|---|---|
| `medium` | 1.5 GB | ~700 MB (int8) | ~0.5s | Multilingual, recommended default |
| `medium.en` | 1.5 GB | ~700 MB (int8) | ~0.5s | English-optimized |
| `large-v3-turbo` | 1.6 GB | ~2.3 GB (float16) | ~0.3s | Fastest but higher VRAM |
| `small` | 466 MB | ~300 MB (int8) | ~0.8s | Low VRAM, lower accuracy |

### Change the model

Edit your systemd service:

```bash
systemctl --user edit mirach
```

Add:

```ini
[Service]
Environment=MIRACH_WHISPER_MODEL=medium.en
Environment=MIRACH_WHISPER_COMPUTE=int8
```

Restart:

```bash
systemctl --user restart mirach
```

The model is downloaded automatically on first use.

## How to add a new locale

### Add strings to i18n.py

Open `~/mirach/mirach/i18n.py` and add a new entry to both `STRINGS` and `FILLERS`:

```python
STRINGS = {
    # ... existing locales ...
    "fr": {
        "recording_start_title": "🎤 Écoute...",
        "recording_start_body": "Appuyez sur {hotkey} pour terminer",
        # ... add all keys ...
    },
}

FILLERS = {
    # ... existing locales ...
    "fr": ["Un moment.", "Je vérifie.", "Hmm."],
}
```

All keys from the English dict must be present. Missing keys fall back to English.

### Set the locale

```ini
[Service]
Environment=MIRACH_LOCALE=fr
```

### Add trigger phrases

If you want built-in triggers (like "show conversation") in your new locale, add them to `BUILTIN_TRIGGERS` in `assistant.py`.

## How to configure persistent memory (Obsidian)

Mirach can read files from your Obsidian vault to restore context across sessions.

### Required vault files

Create these files in your Obsidian vault:

- **`conocimiento.md`** — Persistent instructions and rules
- **`recordatorios.md`** — Pending tasks and reminders
- **`preferencias.md`** — User preferences and habits

### Configure the vault path

```ini
[Service]
Environment=MIRACH_OBSIDIAN_VAULT=/home/you/ObsidianVault
```

### How it works

1. At the start of each new session, Mirach reads these files into RAM
2. Their contents are injected into the LLM prompt as context
3. The cache is refreshed only on new sessions (not every turn)
4. Session timeout defaults to 1 hour of inactivity

## How to view conversation logs

### In the browser (voice command)

Say: "show conversation" or "muéstrame la conversación"

This generates a styled HTML page and opens it in your default browser.

### Raw Markdown files

```bash
# Latest conversation
cat ~/mirach/logs/conversations/latest.md

# All conversations
ls ~/mirach/logs/conversations/
```

### Live daemon logs

```bash
journalctl --user -u mirach -f
```

Or the rotating file log:

```bash
tail -f ~/mirach/logs/daemon.log
```

## How to troubleshoot

### Daemon won't start

```bash
# Check service status
systemctl --user status mirach

# View full logs
journalctl --user -u mirach --no-pager -n 50
```

### CUDA errors

```bash
# Test CUDA availability
~/mirach/venv/bin/python -c "import torch; print(torch.cuda.is_available())"

# Fall back to CPU
systemctl --user edit mirach
# Add: Environment=MIRACH_WHISPER_DEVICE=cpu
```

### OpenCode not responding

```bash
# Test OpenCode directly
opencode run --model opencode/deepseek-v4-flash-free "hello"

# Check auth
opencode auth
```

### Session not persisting

```bash
# Check if session ID is cached
cat ~/.cache/mirach/session_id

# Clear and start fresh
rm ~/.cache/mirach/session_id
systemctl --user restart mirach
```
