---
name: mirach-quick-actions
description: Quick system actions (lock screen, shutdown, reboot, screenshot, nightlight, screen off). Use when the user asks to lock, shut down, restart, take a screenshot, toggle nightlight, or similar quick actions.
---

# Quick Actions

## Power management

| Action | Command |
|---|---|
| Lock screen | `loginctl lock-session` or `hyprlock` |
| Shutdown | `systemctl poweroff` |
| Reboot | `systemctl reboot` |
| Suspend | `systemctl suspend` |
| Hibernate | `systemctl hibernate` |

## Display

| Action | Command |
|---|---|
| Screenshot (full screen) | `omarchy-cmd-screenshot` |
| Screenshot (area) | `grim -g "$(slurp)"` |
| Turn off screen | `hyprctl dispatch dpms off` |
| Turn on screen | `hyprctl dispatch dpms on` |

## Features

| Action | Command |
|---|---|
| Toggle nightlight | `omarchy-toggle-nightlight` |
| Toggle waybar | `omarchy-toggle-waybar` |
| Toggle idle | `omarchy-toggle-idle` |
| Restart Hyprland | `hyprctl reload` |

## Rules

- **Non-destructive actions** (screenshot, lock, nightlight, dpms): execute directly without asking.
- **Destructive actions** (shutdown, reboot): **always confirm first** — "Shutting down in 5 seconds, confirm?" and give a brief countdown.
- Use `omarchy-cmd-shutdown` and `omarchy-cmd-reboot` if available instead of raw systemctl.
- Confirmations: at most 5 words ("Screen locked", "Nightlight on").
