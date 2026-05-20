---
name: mirach-obsidian
description: Obsidian vault management for local memory. Reading and writing notes. Use when the user says "remember", "note", "save this", asks about their notes, or wants to recall personal information.
---

# Obsidian Notes (Local Memory)

The user's Obsidian vault serves as local persistent memory for the assistant.

## Vault location

The vault is located at: `{{obsidian_vault}}`

## Standard note files

The following files are commonly used for structured memory:

| File | Purpose |
|---|---|
| `preferencias.md` | User preferences, likes, habits |
| `proyectos.md` | Active and past projects |
| `recordatorios.md` | Reminders and to-do items |
| `conocimiento.md` | Knowledge base, learned facts |

## Rules

- **"remember X" / "note Y" / "save this"**: Write to the appropriate file in the vault.
- **Before answering personal questions**: Check the vault files first.
- **Reading notes**: Execute directly without asking.
- **Writing notes**: Execute directly for simple additions. If the user wants to overwrite or delete content, confirm first.

## Writing format

Append to the appropriate file using standard markdown. Keep entries concise.

Example for adding a reminder:
```bash
echo "- [ ] New reminder text" >> {{obsidian_vault}}/recordatorios.md
```

## If vault doesn't exist

If `{{obsidian_vault}}` doesn't exist, inform the user and offer to create the directory and standard files.
