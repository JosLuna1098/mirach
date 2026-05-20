---
name: mirach-system-monitor
description: System monitoring commands (btop, htop, free, df, nvidia-smi, ps). Use when the user asks about CPU usage, RAM, disk space, running processes, or system performance.
---

# System Monitor

Commands for checking system status in real-time.

## Quick status commands

| What to check | Command |
|---|---|
| Full system overview | `btop` or `htop` |
| RAM usage | `free -h` |
| Disk usage | `df -h` |
| Disk I/O | `iostat -x 1 1` |
| GPU status | `nvidia-smi` |
| GPU memory | `nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader` |
| Running processes (top 10 by CPU) | `ps aux --sort=-%cpu | head -11` |
| Running processes (top 10 by RAM) | `ps aux --sort=-%mem | head -11` |
| Uptime | `uptime` |
| Load average | `cat /proc/loadavg` |

## Rules

- System monitoring: execute directly without asking.
- Summarize results in 1-2 sentences (TTS output).
- If btop is not installed, suggest `omarchy-install-btop` or `pacman -S btop`.
- For GPU queries, always check if NVIDIA is available first with `nvidia-smi`.
