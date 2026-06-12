# User Scripts Format Reference

User scripts are shell or Python files placed in `<mirach_dir>/user_scripts/` that the daemon parses at startup for trigger phrases.

## File requirements

- Extension must be `.sh` or `.py`
- Must be executable (`chmod +x`)
- Must contain `# triggers:` and `# response:` metadata comments
- Metadata must appear before any non-comment, non-shebang lines

## Metadata format

```bash
#!/bin/bash
# triggers: phrase one, phrase two, phrase three
# response: Text spoken after execution.
# description: Human-readable description (optional).
```

### `# triggers:`

- **Required**
- Comma-separated list of trigger phrases
- Matching is **case-insensitive** and uses **substring matching**
- Example: `focus mode` matches "hey, can you activate focus mode please"

### `# response:`

- **Required**
- Text spoken aloud by TTS after the script runs
- Should be short (1-5 words) for natural conversation flow

### `# description:`

- **Optional**
- Human-readable description for your reference
- Not used by the daemon in any way

## Execution

- Scripts run via `subprocess.Popen` with `start_new_session=True`
- They run in the background — the daemon does not wait for them to complete
- The response is spoken immediately after launching the script
- Standard output and error are not captured

## Parsing rules

1. The parser reads lines from the top of the file
2. Lines starting with `#!` (shebang) are skipped
3. Lines starting with `#` are checked for metadata patterns
4. The first non-comment, non-shebang line ends the metadata block
5. If `triggers` or `response` is missing, the script is skipped with a warning

## Examples

### Simple toggle

```bash
#!/bin/bash
# triggers: toggle nightlight, night light on, night light off
# response: Nightlight toggled.

pkill hyprsunset || (hyprsunset -t 3500 &)
```

### With notification

```bash
#!/bin/bash
# triggers: system status, system info, how is the system
# response: Checking system status.
# description: Shows CPU, memory, and disk usage in a notification

CPU=$(top -bn1 | grep "Cpu(s)" | awk '{printf "%.0f", $2}')
MEM=$(free -h | awk '/Mem:/ {print $3 "/" $2}')
DISK=$(df -h / | awk 'NR==2 {print $3 "/" $2}')
notify-send "System Status" "CPU: ${CPU}%\nMemory: ${MEM}\nDisk: ${DISK}"
```

### Python script

```python
#!/usr/bin/env python3
# triggers: what day is it, what's today, qué día es hoy
# response: Check the notification.

import datetime
import subprocess
today = datetime.datetime.now().strftime("%A, %B %d")
subprocess.run(["notify-send", "Today", today])
```
