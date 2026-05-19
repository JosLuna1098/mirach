#!/usr/bin/env python3
"""Hotkey trigger — runs from Alt+Z (or whatever shortcut is bound).

Standalone: only sends "toggle" to the daemon via its Unix socket. No imports,
no model loading, no extra latency.
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
except (ConnectionRefusedError, FileNotFoundError, socket.timeout):
    subprocess.run(
        ["notify-send", "-i", "dialog-error", "🤖 Mirach",
         "Daemon is not running. Start it with: systemctl --user start mirach"],
        capture_output=True,
    )
    sys.exit(1)
