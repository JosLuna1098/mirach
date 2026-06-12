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
| Screenshot (full screen) | `grim ~/Pictures/screenshot_$(date +%Y%m%d_%H%M%S).png` |
| Screenshot (area) | `grim -g "$(slurp)" ~/Pictures/screenshot_$(date +%Y%m%d_%H%M%S).png` |
| Turn off screen | `hyprctl dispatch dpms off` |
| Turn on screen | `hyprctl dispatch dpms on` |

## Features

| Action | Command |
|---|---|
| Toggle nightlight | `pkill hyprsunset \|\| (hyprsunset -t 3500 &)` |
| Toggle waybar | `pkill -SIGUSR1 waybar` |
| Toggle idle | `systemctl --user stop hypridle` (re-enable: `systemctl --user start hypridle`) |
| Restart Hyprland | `hyprctl reload` |

## Rules

- **Non-destructive actions** (screenshot, lock, nightlight, dpms): execute directly without asking.
- **Destructive actions** (shutdown, reboot): **always confirm first** — "Shutting down in 5 seconds, confirm?" and give a brief countdown.
- Confirmations: at most 5 words ("Screen locked", "Nightlight on").
