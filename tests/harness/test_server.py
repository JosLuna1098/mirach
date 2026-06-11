"""Unit tests for MirachServer (Phase 3 visibility layer).

The server binds to 127.0.0.1:0 (OS-assigned port).  All I/O goes through
urllib and a helper SSE reader — no real daemon, no opencode, no ollama.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from mirach.harness.events import (
    ConversationBus,
    DoneEvent,
    TextDeltaEvent,
)
from mirach.harness.server import DeviceStore, MirachServer, _new_pair_code

# ── FakeAssistant ─────────────────────────────────────────────────────────────


class FakeAssistant:
    def __init__(self) -> None:
        self.bus = ConversationBus()
        self.turns: list[dict] = []
        self.stopped = 0
        self.confirmed: list[str] = []
        self.denied: list[str] = []
        self.resets = 0

    def submit_turn(self, text: str, *, interrupt: bool = False, clear_queue: bool = False) -> dict:
        self.turns.append({"text": text, "interrupt": interrupt, "clear_queue": clear_queue})
        return {"status": "queued", "position": len(self.turns)}

    def stop(self) -> None:
        self.stopped += 1

    def confirm(self, tool_call_id: str) -> None:
        self.confirmed.append(tool_call_id)

    def deny(self, tool_call_id: str) -> None:
        self.denied.append(tool_call_id)

    def reset_session(self) -> None:
        self.resets += 1


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tmpdir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def assistant():
    return FakeAssistant()


@pytest.fixture
def srv(assistant, tmpdir):
    devices_path = tmpdir / "devices.json"
    server = MirachServer(assistant, "127.0.0.1", 0, devices_path=devices_path)
    server.start()
    time.sleep(0.02)  # let the server thread accept connections
    yield server
    server.shutdown()


@pytest.fixture
def base_url(srv):
    _, port = srv.get_address()
    return f"http://127.0.0.1:{port}"


@pytest.fixture
def token(srv, base_url):
    """A valid device token obtained via POST /pair."""
    code = srv._pair_code
    return _pair(base_url, code)["token"]


# ── HTTP helpers ──────────────────────────────────────────────────────────────


def _post(url: str, body: dict, tok: str | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Content-Length", str(len(data)))
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _get(url: str, tok: str | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(url)
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _pair(base_url: str, code: str, device: str = "test") -> dict:
    _, body = _post(f"{base_url}/pair", {"code": code, "device": device})
    return body


def _collect_sse(url: str, tok: str, n: int, timeout: float = 2.0) -> list[dict]:
    """Collect exactly n SSE data frames (or as many as arrive before timeout)."""
    collected: list[dict] = []
    stop = threading.Event()

    def _reader() -> None:
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {tok}")
        try:
            with urllib.request.urlopen(req, timeout=timeout + 1) as resp:
                buf = b""
                while not stop.is_set() and len(collected) < n:
                    chunk = resp.read(1)
                    if not chunk:
                        break
                    buf += chunk
                    if buf.endswith(b"\n\n"):
                        for line in buf.decode().splitlines():
                            if line.startswith("data: "):
                                collected.append(json.loads(line[6:]))
                        buf = b""
                        if len(collected) >= n:
                            stop.set()
        except Exception:
            pass

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    t.join(timeout)
    stop.set()
    return collected


# ── Auth tests ─────────────────────────────────────────────────────────────────


def test_get_events_without_token_returns_401(base_url):
    status, body = _get(f"{base_url}/events")
    assert status == 401
    assert body["error"] == "invalid_token"


def test_post_turn_without_token_returns_401(base_url):
    status, body = _post(f"{base_url}/turn", {"text": "hi"})
    assert status == 401


def test_bearer_header_accepted(base_url, srv):
    """Auth via Authorization: Bearer header (not query string)."""
    tok = _pair(base_url, srv._pair_code)["token"]
    status, body = _post(f"{base_url}/stop", {}, tok)
    assert status == 200


def test_unknown_path_returns_404(base_url, token):
    req = urllib.request.Request(f"{base_url}/nonexistent")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        urllib.request.urlopen(req)
        raise AssertionError("expected 404")
    except urllib.error.HTTPError as e:
        assert e.code == 404


# ── Pairing ────────────────────────────────────────────────────────────────────


def test_pair_invalid_code_returns_403(base_url):
    status, body = _post(f"{base_url}/pair", {"code": "ZZZZZZ"})
    assert status == 403
    assert body["error"] == "invalid_code"


def test_pair_valid_code_returns_token(base_url, srv):
    code = srv._pair_code
    status, body = _post(f"{base_url}/pair", {"code": code, "device": "mobile"})
    assert status == 200
    assert "token" in body
    assert len(body["token"]) > 10


def test_pair_rotates_code_after_use(base_url, srv):
    old_code = srv._pair_code
    _post(f"{base_url}/pair", {"code": old_code})
    # old code no longer valid
    status, _ = _post(f"{base_url}/pair", {"code": old_code})
    assert status == 403


def test_pair_token_persisted_in_devices_json(base_url, srv, tmpdir):
    code = srv._pair_code
    _, body = _post(f"{base_url}/pair", {"code": code, "device": "saved"})
    tok = body["token"]
    data = json.loads((tmpdir / "devices.json").read_text())
    assert tok in data["tokens"]
    assert data["tokens"][tok] == "saved"


def test_loopback_token_written_at_startup(srv, tmpdir):
    data = json.loads((tmpdir / "devices.json").read_text())
    loopback_names = list(data["tokens"].values())
    assert "loopback" in loopback_names


# ── POST /turn ────────────────────────────────────────────────────────────────


def test_turn_calls_submit_turn(base_url, token, assistant):
    status, body = _post(f"{base_url}/turn", {"text": "hello"}, token)
    assert status == 200
    assert len(assistant.turns) == 1
    assert assistant.turns[0]["text"] == "hello"
    assert assistant.turns[0]["interrupt"] is False
    assert assistant.turns[0]["clear_queue"] is False


def test_turn_interrupt_flag_forwarded(base_url, token, assistant):
    _post(f"{base_url}/turn", {"text": "x", "interrupt": True, "clear_queue": True}, token)
    assert assistant.turns[-1]["interrupt"] is True
    assert assistant.turns[-1]["clear_queue"] is True


def test_turn_ack_propagated(base_url, token, assistant):
    _, body = _post(f"{base_url}/turn", {"text": "ack test"}, token)
    assert body["status"] == "queued"
    assert "position" in body


# ── POST /stop ────────────────────────────────────────────────────────────────


def test_stop_calls_assistant_stop(base_url, token, assistant):
    status, _ = _post(f"{base_url}/stop", {}, token)
    assert status == 200
    assert assistant.stopped == 1


# ── POST /confirm + /deny ─────────────────────────────────────────────────────


def test_confirm_relays_tool_call_id(base_url, token, assistant):
    status, _ = _post(f"{base_url}/confirm", {"tool_call_id": "tc-1"}, token)
    assert status == 200
    assert "tc-1" in assistant.confirmed


def test_deny_relays_tool_call_id(base_url, token, assistant):
    status, _ = _post(f"{base_url}/deny", {"tool_call_id": "tc-2"}, token)
    assert status == 200
    assert "tc-2" in assistant.denied


# ── POST /close_session ────────────────────────────────────────────────────────


def test_close_session_calls_reset_session(base_url, token, assistant):
    status, _ = _post(f"{base_url}/close_session", {}, token)
    assert status == 200
    assert assistant.resets == 1


# ── SSE /events ───────────────────────────────────────────────────────────────


def test_sse_streams_live_events(base_url, token, assistant):
    def _publish_after_delay() -> None:
        time.sleep(0.1)
        assistant.bus.publish(TextDeltaEvent(delta="live!"))

    threading.Thread(target=_publish_after_delay, daemon=True).start()
    events = _collect_sse(f"{base_url}/events", token, n=1)
    assert len(events) == 1
    assert events[0]["type"] == "text_delta"
    assert events[0]["delta"] == "live!"


def test_sse_replay_from_since(base_url, token, assistant):
    for i in range(5):
        assistant.bus.publish(DoneEvent(content=f"msg-{i}"))

    events = _collect_sse(f"{base_url}/events?since=3", token, n=2)
    assert len(events) == 2
    assert events[0]["content"] == "msg-3"
    assert events[1]["content"] == "msg-4"


def test_sse_since_zero_replays_all_history(base_url, token, assistant):
    assistant.bus.publish(DoneEvent(content="a"))
    assistant.bus.publish(DoneEvent(content="b"))
    events = _collect_sse(f"{base_url}/events?since=0", token, n=2)
    assert len(events) == 2


def test_sse_two_subscribers_both_receive(base_url, srv, assistant):
    # Pair two separate tokens
    tok1 = _pair(base_url, srv._pair_code)["token"]
    tok2 = _pair(base_url, srv._pair_code)["token"]

    r1: list[dict] = []
    r2: list[dict] = []
    gate = threading.Barrier(3)  # main + 2 readers

    def _reader(tok: str, target: list) -> None:
        req = urllib.request.Request(f"{base_url}/events")
        req.add_header("Authorization", f"Bearer {tok}")
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                gate.wait()  # signal "connected"
                buf = b""
                while len(target) < 1:
                    chunk = resp.read(1)
                    if not chunk:
                        break
                    buf += chunk
                    if buf.endswith(b"\n\n"):
                        for line in buf.decode().splitlines():
                            if line.startswith("data: "):
                                target.append(json.loads(line[6:]))
                        buf = b""
        except Exception:
            gate.wait()  # prevent barrier hang on error

    t1 = threading.Thread(target=_reader, args=(tok1, r1), daemon=True)
    t2 = threading.Thread(target=_reader, args=(tok2, r2), daemon=True)
    t1.start()
    t2.start()
    gate.wait(timeout=2.0)  # wait for both readers to connect
    time.sleep(0.05)  # let both subscribe handlers register

    assistant.bus.publish(TextDeltaEvent(delta="broadcast"))

    t1.join(timeout=2.0)
    t2.join(timeout=2.0)

    assert len(r1) >= 1 and r1[0]["delta"] == "broadcast"
    assert len(r2) >= 1 and r2[0]["delta"] == "broadcast"


def test_sse_attach_is_atomic_no_gap(assistant):
    """Publish events in a tight loop; attach() must not miss any event."""
    bus = assistant.bus
    received: list[object] = []
    publish_count = 50
    ready = threading.Event()

    def _publisher() -> None:
        ready.wait()
        for i in range(publish_count):
            bus.publish(TextDeltaEvent(delta=str(i)))

    pub_thread = threading.Thread(target=_publisher, daemon=True)
    pub_thread.start()

    # Trigger publisher and attach immediately — races are the whole point.
    ready.set()
    replay, unsub = bus.attach(received.append)
    pub_thread.join(timeout=2.0)

    # All published events must be either in replay or delivered via callback.
    # Because attach is atomic, replay + live must cover all events.
    all_events = bus.history()
    assert len(all_events) == publish_count
    assert len(replay) + len(received) >= publish_count

    unsub()


# ── DeviceStore ────────────────────────────────────────────────────────────────


def test_device_store_persists_and_reloads(tmpdir):
    path = tmpdir / "d.json"
    store = DeviceStore(path)
    store.add("tok1", "phone")
    assert store.is_valid("tok1")

    store2 = DeviceStore(path)  # fresh load
    assert store2.is_valid("tok1")
    assert not store2.is_valid("unknown")


def test_device_store_ensure_loopback_idempotent(tmpdir):
    path = tmpdir / "d.json"
    store = DeviceStore(path)
    t1 = store.ensure_loopback()
    t2 = store.ensure_loopback()
    assert t1 == t2  # same token returned each time


def test_pair_code_generator_format():
    for _ in range(20):
        code = _new_pair_code()
        assert len(code) == 6
        assert code.isalnum()
        assert code == code.upper()
