#!/usr/bin/env python3
"""Hotkey trigger — runs from Alt+Z (or whatever shortcut is bound).

Standalone script: only sends "toggle" to the daemon via its Unix socket.
No imports from the mirach package, no model loading, no extra latency.
Exits immediately after sending the message.
"""

import os
import socket
import subprocess
import sys

SOCKET_PATH = os.environ.get("MIRACH_SOCKET", "/tmp/mirach.sock")

try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2)
    s.connect(SOCKET_PATH)
    s.sendall(b"toggle")
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
