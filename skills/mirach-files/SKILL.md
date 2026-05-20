---
name: mirach-files
description: File operations (list, find, open, search content). Use when the user asks to find files, list directory contents, open documents, or search for text within files.
---

# File Operations

## Listing and finding files

| Action | Command |
|---|---|
| List directory | `ls -la <path>` |
| List with sizes | `ls -lah <path>` |
| Find file by name | `find ~ -name "<pattern>" -type f 2>/dev/null` |
| Find recent files | `find ~ -type f -mtime -1 2>/dev/null | head -20` |
| Find large files | `find ~ -type f -size +100M 2>/dev/null | head -10` |
| Search file content | `grep -rl "<text>" ~ --include="*.md" 2>/dev/null | head -10` |
| File type info | `file <path>` |
| Disk usage of dir | `du -sh <path>` |

## Opening files

| Action | Command |
|---|---|
| Open with default app | `xdg-open <path>` |
| Open in terminal editor | `{{shell}} -c "nvim <path>"` or `{{shell}} -c "nano <path>"` |
| Read file content | `cat <path>` or read the file directly |

## Rules

- Reading and searching files: execute directly without asking.
- Opening files: execute directly for documents. Confirm before opening executable files.
- Summarize file listings in 1-2 sentences for TTS.
- If a path is not specified, use the current working directory or `~`.
