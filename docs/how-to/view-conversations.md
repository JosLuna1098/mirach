# How to view conversations

## In the browser (voice command)

Say one of these phrases:

- **English**: "show conversation", "view conversation", "read the conversation"
- **Spanish**: "muéstrame la conversación", "ver conversación", "lee la conversación"

Mirach generates a styled HTML page with a dark theme chat layout and opens it in your default browser.

## Raw Markdown files

```bash
# Latest conversation
cat ~/mirach/logs/conversations/latest.md

# All conversations
ls ~/mirach/logs/conversations/

# Specific conversation
cat ~/mirach/logs/conversations/conversation_2026-01-15_14-30-00.md
```

Each session creates a new timestamped file. `latest.md` is a symlink to the most recent one.

## Live daemon logs

```bash
# Systemd journal (real-time)
journalctl --user -u mirach -f

# Rotating file log
tail -f ~/mirach/logs/daemon.log
```

## Conversation format

Markdown files use this structure:

```markdown
# Conversation 2026-01-15_14-30-00

## You said (14:30:05)

What's the weather today?

---

## Assistant (14:30:12)

It's 22°C and sunny in your area.

---
```

The HTML viewer renders this as a chat-style layout with user messages on the right and assistant messages on the left.
