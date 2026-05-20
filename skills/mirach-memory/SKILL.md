---
name: mirach-memory
description: Persistent memory management using Obsidian vault. Use when the user gives instructions for future sessions, assigns tasks, states preferences, or when you complete an action that creates persistent state (scripts, configs, automations).
---

# Persistent Memory (Obsidian)

You have no memory between sessions unless you explicitly write to the user's Obsidian vault. **This is your only persistent memory.**

## Vault location

`{{obsidian_vault}}`

## Memory files and what goes in each

| File | Purpose | Examples |
|---|---|---|
| `conocimiento.md` | Persistent instructions, rules, automations | "When user says 'modo focus', run ~/scripts/focus.sh", "Always use Spanish for code comments" |
| `recordatorios.md` | Pending tasks, follow-ups, to-dos | "- [ ] Generate backup script for ~/Documents", "- [ ] Research best settings for RTX 5070 Ti" |
| `preferencias.md` | User preferences, habits, tastes | "Prefers dark themes", "Uses fish shell", "Likes minimal UI" |
| `proyectos.md` | Active projects with status | "## Backup automation — In progress. Script at ~/scripts/backup.sh needs cron setup" |

## When to save (CRITICAL)

**Save automatically** — do NOT wait for the user to say "remember this". Save when:

1. **User gives a standing instruction**: "Always do X when I say Y", "From now on..."
2. **You create a persistent artifact**: scripts, config changes, automation rules
3. **User states a preference**: "I like X", "I prefer Y", "Don't do Z"
4. **A task is assigned but not completed**: "Can you look into X later?"
5. **You learn something about the user's workflow**: how they organize files, their routine
6. **User completes or changes a project**: update `proyectos.md` with new status

## How to save

Append to the appropriate file. Use concise entries with timestamps.

```bash
echo "- $(date '+%Y-%m-%d %H:%M'): Instruction details" >> {{obsidian_vault}}/conocimiento.md
```

For checkboxes in `recordatorios.md`:
```bash
echo "- [ ] Task description" >> {{obsidian_vault}}/recordatorios.md
```

To mark a task as done:
```bash
sed -i 's/- \[ \] Old task/- [x] Old task/' {{obsidian_vault}}/recordatorios.md
```

## When starting a new session

At the start of a new conversation (when the system prompt is injected), **read these files first** before responding:

1. `{{obsidian_vault}}/conocimiento.md` — what rules/instructions exist
2. `{{obsidian_vault}}/recordatorios.md` — what tasks are pending
3. `{{obsidian_vault}}/preferencias.md` — user preferences to honor

Use this context to inform your response. If the user asks about something you discussed before, check these files.

## When NOT to save

- Temporary questions ("what time is it?", "how do I do X?")
- One-off commands that are immediately completed ("open firefox")
- Casual conversation without actionable content
- Information the user explicitly says is temporary

## Updating existing entries

If the user changes a preference or completes a task, **update the file** — don't just append. Keep files clean and current.
