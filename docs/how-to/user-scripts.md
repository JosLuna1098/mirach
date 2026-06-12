# How to add a custom voice command (user script)

User scripts let you bypass the LLM and run shell commands directly when you say a trigger phrase. This is instant — no transcription delay beyond the initial STT, no LLM call.

## Create a script

Place a `.sh` or `.py` file in `<mirach_dir>/user_scripts/` with metadata comments at the top:

```bash
#!/bin/bash
# triggers: focus mode, modo focus
# response: Focus mode activated.
# description: Enables focus mode by turning on nightlight and Do Not Disturb

hyprsunset -t 3500 &
notify-send "Focus mode" "Nightlight enabled"
```

## Metadata format

| Comment | Required | Description |
|---|---|---|
| `# triggers:` | Yes | Comma-separated phrases that trigger this script (matched case-insensitively as substrings) |
| `# response:` | Yes | Text spoken aloud after the script runs |
| `# description:` | No | Human-readable description (for your reference, not used by the daemon) |

## How it works

1. The daemon parses all `.sh` and `.py` scripts in `user_scripts/` at startup
2. When you speak, the transcribed text is checked against all trigger phrases (substring match, case-insensitive)
3. If a match is found, the script runs in the background via `subprocess.Popen` and the response is spoken
4. No LLM call is made — this bypasses the entire pipeline after transcription

## Reload scripts

After adding or editing scripts, restart the daemon:

```bash
systemctl --user restart mirach
```

## Example scripts

### Toggle nightlight

```bash
#!/bin/bash
# triggers: nightlight, luz nocturna, night light
# response: Nightlight toggled.
# description: Toggle hyprsunset nightlight

pkill hyprsunset || (hyprsunset -t 3500 &)
```

### System info

```bash
#!/bin/bash
# triggers: system info, info del sistema, system status
# response: Here is your system status.
# description: Show CPU, memory, and disk usage

CPU=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}')
MEM=$(free -h | awk '/Mem:/ {print $3 "/" $2}')
DISK=$(df -h / | awk 'NR==2 {print $3 "/" $2}')
notify-send "System Info" "CPU: ${CPU}%\nMemory: ${MEM}\nDisk: ${DISK}"
```

### Open an app

```bash
#!/bin/bash
# triggers: open browser, abrir navegador, launch firefox
# response: Opening browser.
# description: Launch Firefox

firefox &
```
