---
name: mirach-apps
description: Opening applications, launching terminals with visible commands, and starting music. Use when the user asks to open, launch, or start any application.
---

# App Management

## Opening apps

Launch applications detached from the shell so they survive the session:

```
setsid -f <app-name>
```

Examples:
- `setsid -f firefox`
- `setsid -f discord`
- `setsid -f obsidian`

> **Note (uwsm sessions):** In sessions managed by uwsm (Omarchy / Hyprland+uwsm), prefer
> `uwsm-app -- <app>` to place the app in its own systemd scope.

## Terminal with visible command

When the user wants to see a terminal running a command:

```
setsid -f {{terminal}} -e {{shell}} -c "command; exec {{shell}}"
```

This opens a terminal, runs the command, and keeps the shell open afterward.

## Music player

{{music_player}}

## Rules

- Opening apps: execute directly without asking for confirmation.
- If the app name is unknown, try to find it with `which <app>` or `flatpak list | grep -i <app>` before giving up.
- Confirmations of opening apps: at most 5 words ("Firefox abierto", "Done").
