"""Hotkey trigger — sends a single "toggle" message to the running daemon."""

from __future__ import annotations

import socket
import subprocess
import sys

from mirach import config, i18n


def main() -> int:
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(config.SOCKET_PATH)
        s.sendall(b"toggle")
        s.close()
        return 0
    except (TimeoutError, ConnectionRefusedError, FileNotFoundError):
        subprocess.run(
            [
                "notify-send",
                "-i",
                "dialog-error",
                i18n.t("assistant"),
                i18n.t("daemon_not_running"),
            ],
            capture_output=True,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
