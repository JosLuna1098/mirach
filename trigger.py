#!/usr/bin/env python3
"""Hotkey trigger — runs from Alt+Z (or whatever shortcut is bound).

Standalone script: sends a command to the daemon via its Unix socket.
  trigger.py          → "toggle" (record / send / interrupt — the Alt+Z key)
  trigger.py stop     → "stop"   (hard stop: cancel current run + clear queue)
No imports from the mirach package, no model loading, no extra latency.
Exits immediately after sending the message.
"""

import os
import socket
import subprocess
import sys

SOCKET_PATH = os.environ.get("MIRACH_SOCKET", "/tmp/mirach.sock")

message = b"stop" if len(sys.argv) > 1 and sys.argv[1] == "stop" else b"toggle"

try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2)
    s.connect(SOCKET_PATH)
    s.sendall(message)
    s.close()
except (ConnectionRefusedError, FileNotFoundError, TimeoutError):
    # Daemon not running — notify the user via desktop notification
    subprocess.run(
        [
            "notify-send",
            "-i",
            "dialog-error",
            "🤖 Mirach",
            "Daemon is not running. Start it with: systemctl --user start mirach",
        ],
        capture_output=True,
    )
    sys.exit(1)
