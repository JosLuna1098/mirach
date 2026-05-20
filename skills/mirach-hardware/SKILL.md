---
name: mirach-hardware
description: Hardware status queries (GPU, CPU, temps, overclocking, ECC errors). Use when the user asks about GPU status, temperatures, overclocking, stress tests, or hardware health. Read hardware.md from the vault if it exists.
---

# Hardware Status

## Primary hardware file

When the user asks about GPU status, temperatures, overclocking, ECC errors, or stress tests, **first check if this file exists and read it**:

{{hardware_file}}

If the file exists, use its contents to answer. It contains the user's hardware configuration, OC settings, ECC error logs, and temperature baselines.

If the file does NOT exist, fall back to live system commands.

## Live commands for hardware info

| Query | Command |
|---|---|
| GPU info | `nvidia-smi` |
| GPU temps | `nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader` |
| CPU temps | `sensors` or `cat /sys/class/thermal/thermal_zone*/temp` |
| CPU usage | `top -bn1 | head -20` or `htop` |
| RAM usage | `free -h` |
| Disk usage | `df -h` |
| Stress test | `stress-ng --cpu 0 --timeout 60s` (confirm before running) |

## Rules

- Reading hardware status: execute directly without asking.
- Running stress tests: **always confirm first** — they stress the hardware.
- If the user asks about OC (overclocking), warn about risks and reference the hardware file if it has OC settings documented.
