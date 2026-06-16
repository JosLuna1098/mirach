"""Local HTTP/SSE visibility server for Phase 3 (widget + mobile API).

Endpoints
---------
GET  /                         — Widget HTML (loopback only; token injected).
GET  /events?token=T&since=N   — SSE stream of ConversationBus events.
                                  `since` = event index for replay (default 0).
POST /pair      {code, device?} — Exchange a displayed pairing code for a
                                  long-lived device token. No auth required.
POST /turn        {text, interrupt?, clear_queue?}
POST /stop        {}
POST /confirm     {tool_call_id}
POST /deny        {tool_call_id}
POST /close_session {}
POST /clear_queue {}

Auth
----
Every endpoint except /pair requires a valid device token, passed either as
?token=T in the query string or as an "Authorization: Bearer T" header.
Tokens are stored in ~/.config/mirach/devices.json.

A permanent "loopback" token is created at startup for the local widget.
"""

from __future__ import annotations

import json
import queue
import secrets
import string
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from mirach.harness._widget import WIDGET_HTML
from mirach.logging_setup import log

if TYPE_CHECKING:
    from mirach.assistant import Assistant


# ── Pairing code helpers ─────────────────────────────────────────────────────

_CODE_CHARS = string.ascii_uppercase + string.digits


def _new_pair_code() -> str:
    return "".join(secrets.choice(_CODE_CHARS) for _ in range(6))


# ── Device store ─────────────────────────────────────────────────────────────


class DeviceStore:
    """Thread-safe store for device tokens in ~/.config/mirach/devices.json.

    File format: {"tokens": {"<token>": "<device_name>"}}
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._tokens: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                self._tokens = data.get("tokens", {})
            except Exception:
                self._tokens = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({"tokens": self._tokens}, indent=2))

    def is_valid(self, token: str) -> bool:
        with self._lock:
            return bool(token) and token in self._tokens

    def add(self, token: str, name: str) -> None:
        with self._lock:
            self._tokens[token] = name
            self._save()

    def ensure_loopback(self) -> str:
        """Return the loopback token, creating and persisting one if absent."""
        with self._lock:
            for token, name in self._tokens.items():
                if name == "loopback":
                    return token
            token = secrets.token_urlsafe(32)
            self._tokens[token] = "loopback"
            self._save()
            return token


# ── HTTP server ───────────────────────────────────────────────────────────────

_SSE_HEARTBEAT_SEC = 15


class MirachServer:
    """ThreadingHTTPServer wrapper that bridges the Assistant to remote clients.

    Usage::

        server = MirachServer(assistant, host, port, devices_path)
        host, port = server.start()   # starts a daemon thread
    """

    def __init__(
        self,
        assistant: Assistant,
        host: str = "127.0.0.1",
        port: int = 7270,
        devices_path: Path | None = None,
    ) -> None:
        self._assistant = assistant
        if devices_path is None:
            devices_path = Path.home() / ".config" / "mirach" / "devices.json"
        self._devices = DeviceStore(devices_path)
        self._pair_lock = threading.Lock()
        self._pair_code = _new_pair_code()
        self._server: ThreadingHTTPServer | None = None

        self._httpd = ThreadingHTTPServer((host, port), self._make_handler_class())
        self._httpd.daemon_threads = True

    def start(self) -> tuple[str, int]:
        """Start serving in a daemon thread. Returns (host, actual_port)."""
        loopback = self._devices.ensure_loopback()
        host, port = self._httpd.server_address
        log.info("HTTP API server on %s:%d", host, port)
        log.info("Widget: http://%s:%d/", host, port)
        log.info("Pairing code: %s", self._pair_code)
        log.info("Loopback token: %s", loopback)
        t = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        t.start()
        return host, port

    def get_address(self) -> tuple[str, int]:
        return self._httpd.server_address  # type: ignore[return-value]

    def get_loopback_token(self) -> str:
        return self._devices.ensure_loopback()

    def shutdown(self) -> None:
        self._httpd.shutdown()

    # ── Request routing ───────────────────────────────────────────────────────

    def _make_handler_class(self) -> type:
        server = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: object) -> None:  # type: ignore[override]
                log.debug("HTTP " + fmt, *args)

            def do_GET(self) -> None:
                path = urlparse(self.path).path
                if path == "/":
                    server._handle_root(self)
                elif path == "/events":
                    server._handle_events(self)
                else:
                    server._send_json(self, 404, {"error": "not_found"})

            def do_POST(self) -> None:
                path = urlparse(self.path).path
                _routes: dict[str, object] = {
                    "/pair": server._handle_pair,
                    "/turn": server._handle_turn,
                    "/stop": server._handle_stop,
                    "/confirm": server._handle_confirm,
                    "/deny": server._handle_deny,
                    "/close_session": server._handle_close_session,
                    "/clear_queue": server._handle_clear_queue,
                }
                fn = _routes.get(path)
                if fn is None:
                    server._send_json(self, 404, {"error": "not_found"})
                else:
                    fn(self)  # type: ignore[operator]

        return _Handler

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _send_json(handler: BaseHTTPRequestHandler, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)

    def _check_auth(self, handler: BaseHTTPRequestHandler) -> bool:
        qs = parse_qs(urlparse(handler.path).query)
        token = qs.get("token", [""])[0]
        if not token:
            auth = handler.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
        if self._devices.is_valid(token):
            return True
        self._send_json(handler, 401, {"error": "invalid_token"})
        return False

    def _read_json(self, handler: BaseHTTPRequestHandler) -> dict | None:
        try:
            length = int(handler.headers.get("Content-Length", 0))
            raw = handler.rfile.read(length) if length > 0 else b"{}"
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            self._send_json(handler, 400, {"error": "invalid_json"})
            return None

    # ── Route handlers ────────────────────────────────────────────────────────

    def _handle_events(self, handler: BaseHTTPRequestHandler) -> None:
        if not self._check_auth(handler):
            return
        qs = parse_qs(urlparse(handler.path).query)
        try:
            since = int(qs.get("since", ["0"])[0])
        except ValueError:
            since = 0

        q: queue.Queue = queue.Queue()
        bus = self._assistant.bus
        replay, unsub = bus.attach(q.put, since=since)

        try:
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream")
            handler.send_header("Cache-Control", "no-cache")
            handler.send_header("Connection", "keep-alive")
            handler.send_header("X-Accel-Buffering", "no")
            handler.end_headers()

            for event in replay:
                _write_sse_frame(handler, event)
            handler.wfile.flush()

            while True:
                try:
                    event = q.get(timeout=_SSE_HEARTBEAT_SEC)
                    _write_sse_frame(handler, event)
                    handler.wfile.flush()
                except queue.Empty:
                    handler.wfile.write(b":\n\n")
                    handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            unsub()

    def _handle_pair(self, handler: BaseHTTPRequestHandler) -> None:
        body = self._read_json(handler)
        if body is None:
            return
        code = body.get("code", "")
        device = body.get("device", "unknown")
        with self._pair_lock:
            if code != self._pair_code:
                self._send_json(handler, 403, {"error": "invalid_code"})
                return
            token = secrets.token_urlsafe(32)
            self._devices.add(token, device)
            self._pair_code = _new_pair_code()
            log.info("New device paired: %s", device)
        self._send_json(handler, 200, {"token": token})

    def _handle_turn(self, handler: BaseHTTPRequestHandler) -> None:
        if not self._check_auth(handler):
            return
        body = self._read_json(handler)
        if body is None:
            return
        text = body.get("text", "")
        interrupt = bool(body.get("interrupt", False))
        clear_queue = bool(body.get("clear_queue", False))
        result = self._assistant.submit_turn(text, interrupt=interrupt, clear_queue=clear_queue)
        self._send_json(handler, 200, result)

    def _handle_stop(self, handler: BaseHTTPRequestHandler) -> None:
        if not self._check_auth(handler):
            return
        self._assistant.stop()
        self._send_json(handler, 200, {"status": "ok"})

    def _handle_confirm(self, handler: BaseHTTPRequestHandler) -> None:
        if not self._check_auth(handler):
            return
        body = self._read_json(handler)
        if body is None:
            return
        self._assistant.confirm(body.get("tool_call_id", ""))
        self._send_json(handler, 200, {"status": "ok"})

    def _handle_deny(self, handler: BaseHTTPRequestHandler) -> None:
        if not self._check_auth(handler):
            return
        body = self._read_json(handler)
        if body is None:
            return
        self._assistant.deny(body.get("tool_call_id", ""))
        self._send_json(handler, 200, {"status": "ok"})

    def _handle_close_session(self, handler: BaseHTTPRequestHandler) -> None:
        if not self._check_auth(handler):
            return
        self._assistant.reset_session()
        self._send_json(handler, 200, {"status": "ok"})

    def _handle_clear_queue(self, handler: BaseHTTPRequestHandler) -> None:
        if not self._check_auth(handler):
            return
        self._assistant.clear_queue()
        self._send_json(handler, 200, {"status": "ok"})

    def _handle_root(self, handler: BaseHTTPRequestHandler) -> None:
        """Serve the widget HTML, but only to loopback clients.

        Non-loopback is rejected (403) so the loopback token is never leaked
        if the server is later bound to a LAN/Tailscale interface.
        """
        ip = handler.client_address[0]
        if ip not in ("127.0.0.1", "::1"):
            self._send_json(handler, 403, {"error": "loopback_only"})
            return
        token = self._devices.ensure_loopback()
        html = WIDGET_HTML.replace("__MIRACH_TOKEN__", token)
        data = html.encode()
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)


# ── SSE frame serializer ──────────────────────────────────────────────────────


def _write_sse_frame(handler: BaseHTTPRequestHandler, event: object) -> None:
    payload = json.dumps(event.to_dict()).encode()  # type: ignore[attr-defined]
    handler.wfile.write(b"data: " + payload + b"\n\n")
