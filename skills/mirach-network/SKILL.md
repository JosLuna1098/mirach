---
name: mirach-network
description: Network management (WiFi, Bluetooth, connectivity) using nmcli, bluetoothctl, ping, and related tools. Use when the user asks about network status, WiFi connections, Bluetooth devices, or connectivity issues.
---

# Network Management

## WiFi (nmcli)

| Action | Command |
|---|---|
| List WiFi networks | `nmcli device wifi list` |
| Current connection | `nmcli -t -f active,ssid dev wifi | grep '^yes'` |
| Connect to network | `nmcli device wifi connect <SSID> password <pass>` |
| Disconnect | `nmcli device disconnect wlan0` |
| WiFi on/off | `nmcli radio wifi on` / `nmcli radio wifi off` |

## Bluetooth (bluetoothctl)

| Action | Command |
|---|---|
| List paired devices | `bluetoothctl paired-devices` |
| Scan for devices | `bluetoothctl scan on` (run for 10s then stop) |
| Connect to device | `bluetoothctl connect <MAC>` |
| Disconnect | `bluetoothctl disconnect <MAC>` |
| Bluetooth on/off | `bluetoothctl power on` / `bluetoothctl power off` |

## Connectivity

| Action | Command |
|---|---|
| Ping host | `ping -c 4 <host>` |
| Check DNS | `nslookup <host>` or `dig <host>` |
| External IP | `curl -s ifconfig.me` |
| Network interfaces | `ip addr show` |
| Default gateway | `ip route show default` |
| Download speed test | `speedtest-cli` (if installed) |

## Rules

- Network status checks: execute directly without asking.
- Connecting/disconnecting: confirm first (especially WiFi password entry).
- Summarize results in 1-2 sentences for TTS.
