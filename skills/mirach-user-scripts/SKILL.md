---
name: mirach-user-scripts
description: Creating and managing user scripts for voice-triggered actions. Use when the user asks to create a custom voice command, automate an action triggered by a phrase, or set up a recurring task triggered by voice.
---

# User Scripts

Mirach supports custom voice-triggered scripts. Users can create scripts in the `user_scripts/` directory that execute automatically when specific phrases are spoken.

## Directory

Scripts go in: `{{mirach_dir}}/user_scripts/`

## Script format

Every script must start with metadata comments in the first few lines:

```bash
#!/bin/bash
# triggers: phrase one, phrase two, phrase three
# response: Spoken confirmation the assistant says after running the script.
# description: Brief description of what this script does.

# Your script logic here
```

### Metadata fields

| Field | Required | Description |
|---|---|---|
| `triggers` | Yes | Comma-separated list of voice phrases that trigger this script. Include variations the user might say. |
| `response` | Yes | Short spoken confirmation (max 5 words — goes to TTS). |
| `description` | No | Brief description for documentation purposes. |

## Rules

- **File extensions**: `.sh` for bash scripts, `.py` for Python scripts.
- **Make executable**: Always run `chmod +x <script>` after creating.
- **Triggers are case-insensitive**: The daemon matches against lowercase text.
- **Keep responses short**: They go through TTS. Max 5 words.
- **Do not modify existing scripts** unless the user explicitly asks to change them.
- **Check for conflicts**: Before creating a new script, check if any existing trigger overlaps with an existing one. If it does, warn the user.

## Creating a new script

1. Choose a descriptive filename: `user_scripts/<action_name>.sh`
2. Write the script with the required metadata header
3. Make it executable: `chmod +x {{mirach_dir}}/user_scripts/<action_name>.sh`
4. Confirm to the user what phrases will trigger it and what it does.

## Example

User: "When I say 'focus mode', turn on nightlight, close Discord, and play lofi music."

You create `user_scripts/focus_mode.sh`:

```bash
#!/bin/bash
# triggers: focus mode, modo focus, modo concentracion, concentrarme
# response: Modo focus activado.
# description: Enables focus mode: nightlight on, Discord closed, lofi playing

hyprsunset -t 3500 &
pkill -i discord 2>/dev/null
mpv --no-video --really-quiet "https://www.youtube.com/watch?v=jfKfPfyJRdk" &
disown
```

Then run: `chmod +x {{mirach_dir}}/user_scripts/focus_mode.sh`

## Listing existing scripts

To see what scripts exist and their triggers:

```bash
for f in {{mirach_dir}}/user_scripts/*.sh; do
    echo "=== $(basename "$f") ==="
    head -3 "$f"
    echo
done
```

## Deleting a script

```bash
rm {{mirach_dir}}/user_scripts/<script_name>.sh
```

Confirm with the user before deleting.
