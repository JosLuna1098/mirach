---
name: mirach-git
description: Git repository operations (status, log, diff, commit, push, branch). Use when the user asks about git status, recent commits, differences, or wants to perform git operations.
---

# Git Operations

## Common commands

| Action | Command |
|---|---|
| Status | `git status` |
| Recent commits (last 10) | `git log --oneline -10` |
| Detailed log | `git log --pretty=format:"%h - %an, %ar : %s" -10` |
| Diff (unstaged) | `git diff` |
| Diff (staged) | `git diff --staged` |
| Diff summary | `git diff --stat` |
| Current branch | `git branch --show-current` |
| List branches | `git branch -a` |
| Untracked files | `git ls-files --others --exclude-standard` |

## Write operations (confirm first)

| Action | Command |
|---|---|
| Stage all | `git add .` |
| Stage file | `git add <file>` |
| Commit | `git commit -m "message"` |
| Push | `git push` |
| Push (new branch) | `git push -u origin <branch>` |
| Create branch | `git checkout -b <branch>` |
| Stash | `git stash` |
| Stash pop | `git stash pop` |

## Rules

- **Read operations** (status, log, diff): execute directly without asking.
- **Write operations** (add, commit, push, branch creation): **always confirm first** — describe what you will do and wait for approval.
- Summarize git status in 1-2 sentences for TTS.
- If not in a git repo, inform the user.
