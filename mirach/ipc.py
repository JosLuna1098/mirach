"""Unix domain socket server for daemon-client communication.

Listens on a socket path (default /tmp/mirach.sock) and dispatches messages:
  - "toggle" → triggers the assistant FSM (record/process/interrupt cycle)
  - "ping"   → replies "pong" for health checks

Each connection is handled synchronously; the server runs in the main thread.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Callable

from mirach import config
from mirach.logging_setup import log


class SocketServer:
    """Blocking Unix socket server that dispatches to a toggle callback."""

    def __init__(self, on_toggle: Callable[[], None]) -> None:
        self._on_toggle = on_toggle

    def serve_forever(self) -> None:
        """Bind to the socket and accept connections indefinitely."""
        if os.path.exists(config.SOCKET_PATH):
            os.remove(config.SOCKET_PATH)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(config.SOCKET_PATH)
        srv.listen(5)
        log.info("Listening on %s", config.SOCKET_PATH)

        while True:
            conn, _ = srv.accept()
            try:
                data = conn.recv(64).decode().strip()
                if data == "toggle":
                    self._on_toggle()
                elif data == "ping":
                    conn.sendall(b"pong")
                else:
                    log.warning("Unknown socket message: %r", data)
            except Exception as e:
                log.exception("Connection error: %s", e)
            finally:
                conn.close()
