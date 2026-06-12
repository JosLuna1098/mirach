---
name: mirach-system
description: Hyprland/Arch Linux/systemd system management. Use when the user asks about managing windows, services, screenshots, display settings, nightlight, wallpaper, fonts, or any Hyprland/Arch desktop task.
---

# System Management (Hyprland + Arch Linux)

## Principle

Before assuming a tool exists, verify with `which <tool>`. Prefer generic,
discoverable commands; let bash reveal what is installed on this machine.

## Hyprland — compositor control

| Task | Command |
|---|---|
| Reload config | `hyprctl reload` |
| List windows | `hyprctl clients` |
| List monitors | `hyprctl monitors` |
| Dispatch action | `hyprctl dispatch <action> <args>` |
| Turn display off | `hyprctl dispatch dpms off` |
| Turn display on | `hyprctl dispatch dpms on` |
| Active window | `hyprctl activewindow` |
| Switch workspace | `hyprctl dispatch workspace <N>` |

Config files: `~/.config/hypr/`

## Services — systemctl

| Task | Command |
|---|---|
| Status of user service | `systemctl --user status <service>` |
| Restart user service | `systemctl --user restart <service>` |
| List running user services | `systemctl --user list-units --state=running` |
| System service (root) | `sudo systemctl <action> <service>` |

## Screenshots

| Task | Command |
|---|---|
| Full screen | `grim ~/Pictures/screenshot_$(date +%Y%m%d_%H%M%S).png` |
| Area selection | `grim -g "$(slurp)" ~/Pictures/screenshot_$(date +%Y%m%d_%H%M%S).png` |

## Nightlight / color temperature

```bash
# Check if hyprsunset is available
which hyprsunset

# Enable (warm color, ~3500 K)
hyprsunset -t 3500 &

# Disable
pkill hyprsunset
```

See also `~/.config/hypr/hyprsunset.conf` if a config is present.

## Status bar (Waybar)

```bash
# Toggle visibility
pkill -SIGUSR1 waybar

# Restart
pkill waybar; waybar &
```

## Idle daemon (hypridle)

```bash
systemctl --user stop hypridle    # disable idle
systemctl --user start hypridle   # re-enable
systemctl --user status hypridle
```

## Package management (Arch / CachyOS)

| Task | Command |
|---|---|
| Install | `sudo pacman -S <pkg>` |
| Remove | `sudo pacman -R <pkg>` |
| Search | `pacman -Ss <query>` |
| Update system | `sudo pacman -Syu` |
| AUR helper | `which yay paru` — check what is available first |

## Fonts

```bash
fc-list | sort          # list all installed fonts
fc-list | grep -i <name>
```

Set a font by editing `~/.config/<app>/config` for each application.

## Config edit pattern

1. Read the current config.
2. Back it up: `cp ~/.config/<app>/config ~/.config/<app>/config.bak`
3. Edit, preserving existing structure and comments.
4. Reload: `hyprctl reload` for Hyprland, or `systemctl --user restart <svc>` for services.
