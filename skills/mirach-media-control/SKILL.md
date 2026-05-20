---
name: mirach-media-control
description: Media playback control (volume, pause, play, next, previous) using playerctl, pactl, and amixer. Use when the user asks to change volume, pause music, skip tracks, or control media playback.
---

# Media Control

## Volume control

| Action | Command |
|---|---|
| Increase volume 5% | `pactl set-sink-volume @DEFAULT_SINK@ +5%` |
| Decrease volume 5% | `pactl set-sink-volume @DEFAULT_SINK@ -5%` |
| Set volume to X% | `pactl set-sink-volume @DEFAULT_SINK@ X%` |
| Mute/unmute | `pactl set-sink-mute @DEFAULT_SINK@ toggle` |
| Check current volume | `pactl get-sink-volume @DEFAULT_SINK@` |

## Media playback (playerctl)

| Action | Command |
|---|---|
| Play/pause | `playerctl play-pause` |
| Play | `playerctl play` |
| Pause | `playerctl pause` |
| Next track | `playerctl next` |
| Previous track | `playerctl previous` |
| Check status | `playerctl status` |
| Current track | `playerctl metadata title` |
| Current artist | `playerctl metadata artist` |

## Rules

- Media control: execute directly without asking.
- Confirmations: at most 5 words ("Volume up", "Paused", "Next track").
- If playerctl is not installed, suggest `pacman -S playerctl`.
- For browser-based music (YouTube Music), playerctl may not work — inform the user.
