---
name: mirach-apps
description: Opening applications, launching terminals with visible commands, and starting music. Use when the user asks to open, launch, or start any application.
---

# App Management

## Opening apps

Always use `uwsm-app --` to launch applications on this system (Omarchy/Hyprland).

```
uwsm-app -- <app-name>
```

Examples:
- `uwsm-app -- firefox`
- `uwsm-app -- discord`
- `uwsm-app -- obsidian`

## Terminal with visible command

When the user wants to see a terminal running a command:

```
uwsm-app -- ghostty -e {{shell}} -c "command; exec {{shell}}"
```

This opens a terminal, runs the command, and keeps the shell open afterward.

## Music player

{{music_player}}

## Rules

- Opening apps: execute directly without asking for confirmation.
- If the app name is unknown, try to find it with `which <app>` or `flatpak list | grep -i <app>` before giving up.
- Confirmations of opening apps: at most 5 words ("Firefox abierto", "Done").
