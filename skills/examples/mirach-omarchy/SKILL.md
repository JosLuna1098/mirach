---
name: mirach-omarchy-example
description: "Example skill for Omarchy-based setups. Archive — not installed by default. Activate instead of (or alongside) mirach-system if you run Omarchy."
---

<!--
  EXAMPLE SKILL — not installed by default.
  For users running Omarchy (https://omarchy.org) on top of Arch+Hyprland.
  To activate: add an entry to ALL_CAPABILITIES in install.py and re-run the installer.
-->

# Omarchy Management

Omarchy is a layer on top of Arch Linux + Hyprland.

## GOLDEN RULE

**NEVER** edit files in `~/.local/share/omarchy/` (those are core files). User configuration goes in `~/.config/`.

## Command categories

Omarchy provides ~145 commands following the pattern `omarchy-<category>-<action>`:

| Category | Purpose | Examples |
|---|---|---|
| `omarchy-theme-*` | Themes | `omarchy-theme-set`, `omarchy-theme-list`, `omarchy-theme-next`, `omarchy-theme-bg-next`, `omarchy-theme-current` |
| `omarchy-restart-*` | Restart services | `omarchy-restart-waybar`, `omarchy-restart-hypridle`, `omarchy-restart-terminal` |
| `omarchy-refresh-*` | Reset config to defaults | `omarchy-refresh-<app>` (makes backup first) |
| `omarchy-toggle-*` | Toggle features | `omarchy-toggle-nightlight`, `omarchy-toggle-waybar`, `omarchy-toggle-idle` |
| `omarchy-launch-*` | Launch apps | `omarchy-launch-browser`, `omarchy-launch-editor`, `omarchy-launch-webapp` |
| `omarchy-cmd-*` | System commands | `omarchy-cmd-screenshot`, `omarchy-cmd-screenrecord`, `omarchy-cmd-reboot`, `omarchy-cmd-shutdown` |
| `omarchy-pkg-*` | Packages | `omarchy-pkg-install`, `omarchy-pkg-remove` |
| `omarchy-install-*` | Install optional software | Various |
| `omarchy-font-*` | Fonts | `omarchy-font-list`, `omarchy-font-current`, `omarchy-font-set` |
| `omarchy-menu-*` | Menus | `omarchy-menu-keybindings` |

## Discovering commands

To find the exact command for a task:
```
ls ~/.local/share/omarchy/bin/ | grep omarchy-<filter>
```

To understand what a command does:
```
cat $(which omarchy-theme-set)
```

## Config locations (~/.config/)

- **Hyprland**: `~/.config/hypr/` — hyprland.lua, bindings.lua, monitors.lua, input.lua, looknfeel.lua, hypridle.conf, hyprlock.conf, hyprsunset.conf
- **Waybar** (status bar): `~/.config/waybar/config.jsonc` and `style.css`
- **Walker** (launcher): `~/.config/walker/config.toml`
- **Terminals**: `~/.config/alacritty/alacritty.toml`, `~/.config/ghostty/config`
- **Others**: btop, fastfetch, lazygit, starship — all in `~/.config/<app>/`

## Common tasks

- Change theme: `omarchy-theme-set <name>`
- Change wallpaper: `omarchy-theme-bg-next`
- Restart the bar: `omarchy-restart-waybar`
- Reset a broken config: `omarchy-refresh-<app>` (makes backup first)
- Night light: `omarchy-toggle-nightlight`
- Screenshot: `omarchy-cmd-screenshot`
- System font: `omarchy-font-set <name>`
- Update the system: `omarchy-update`
- Monitors: edit `~/.config/hypr/monitors.lua`; view with `hyprctl monitors`
- Keybindings: edit `~/.config/hypr/bindings.lua` (Hyprland reloads on save)

## Safe config edit pattern

1. Read the current config
2. Make a backup (`cp config config.bak`)
3. Edit preserving structure and comments
4. Apply: `omarchy-restart-<app>` (or Hyprland reloads on save)

## Official manual

For "how do I...?" questions, the official manual is at https://learn.omacom.io
