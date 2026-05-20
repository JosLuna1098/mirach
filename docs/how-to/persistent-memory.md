# How to configure persistent memory (Obsidian)

Mirach can read files from your Obsidian vault to restore context across sessions. This gives the LLM continuity — it remembers your preferences, pending tasks, and rules.

## Required vault files

Create these files in your Obsidian vault:

- **`conocimiento.md`** — Persistent instructions and rules the assistant should always follow
- **`recordatorios.md`** — Pending tasks, reminders, and things to follow up on
- **`preferencias.md`** — User preferences: language, tone, favorite tools, habits

These files are read at the start of each new session and injected into the LLM prompt as context.

## Configure the vault path

```bash
systemctl --user edit mirach
```

Add:

```ini
[Service]
Environment=MIRACH_OBSIDIAN_VAULT=/home/you/ObsidianVault
```

## How it works

1. At the start of each new LLM session (after `SESSION_IDLE_TIMEOUT` of inactivity), Mirach reads these files from disk into RAM
2. Their contents are formatted and injected into the system prompt before the first query
3. The cache is **not** refreshed on every turn — only on new sessions
4. This means you can edit the vault files between sessions and the changes will be picked up

## Session timeout

The default idle timeout is 1 hour (`MIRACH_SESSION_IDLE_TIMEOUT=3600`). After 1 hour of no interactions, the next hotkey press starts a fresh session and reloads the Obsidian context.

To change:

```ini
[Service]
Environment=MIRACH_SESSION_IDLE_TIMEOUT=1800
```

(30 minutes in this example)

## Session persistence across restarts

The OpenCode session ID is saved to `~/.cache/mirach/session_id`. This means:

- If the daemon restarts (systemd restart, crash recovery), the conversation continues
- If the system reboots, the session survives as long as the timeout hasn't elapsed
- To force a fresh session: `rm ~/.cache/mirach/session_id && systemctl --user restart mirach`
