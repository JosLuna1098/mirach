---
name: mirach-obsidian
description: Obsidian vault file operations. Reading, searching, and writing notes. Use when the user asks to read their notes, search within notes, or manage vault files. For persistent memory rules, see mirach-memory skill.
---

# Obsidian Notes

The user's Obsidian vault is at: `{{obsidian_vault}}`

## Standard note files

| File | Purpose |
|---|---|
| `preferencias.md` | User preferences, likes, habits |
| `proyectos.md` | Active and past projects |
| `recordatorios.md` | Reminders and to-do items |
| `conocimiento.md` | Knowledge base, learned facts, persistent instructions |

## Rules

- **Reading notes**: Execute directly without asking.
- **Writing notes**: Execute directly for simple additions. If the user wants to overwrite or delete content, confirm first.
- **Before answering personal questions**: Check the vault files first.

## Writing format

Append to the appropriate file using standard markdown. Keep entries concise.

```bash
echo "- [ ] New reminder text" >> {{obsidian_vault}}/recordatorios.md
```

## Persistent memory

For rules about **when** and **what** to save as persistent memory across sessions, see the `mirach-memory` skill. This skill handles the file operations; `mirach-memory` handles the decision logic.

## If vault doesn't exist

If `{{obsidian_vault}}` doesn't exist, inform the user and offer to create the directory and standard files.
