#!/usr/bin/env python3
"""Mobile-readiness gate: exercises every endpoint in the Mirach HTTP contract.

Starts its own MirachServer with a FakeAssistant on a random port — no real
daemon required.  Prints OK / FAIL per scenario; exits 1 if any fail.

Run:
    python tools/client.py

Against a real daemon (supply its base URL and a token or pair code):
    python tools/client.py --url http://127.0.0.1:7270 --token <loopback-token>
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Minimal FakeAssistant (no audio / STT / TTS / real LLM)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mirach.harness.events import ConversationBus, DoneEvent, TextDeltaEvent  # noqa: E402
from mirach.harness.server import MirachServer  # noqa: E402


class FakeAssistant:
    def __init__(self) -> None:
        self.bus = ConversationBus()
        self.turns: list[dict] = []
        self.stopped: int = 0
        self.confirmed: list[str] = []
        self.denied: list[str] = []
        self.sessions_reset: int = 0

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
        self.sessions_reset += 1


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _post(url: str, body: dict, token: str | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Content-Length", str(len(data)))
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _get_json(url: str, token: str | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _collect_sse(url: str, token: str, n_events: int, timeout: float = 3.0) -> list[dict]:
    """Connect to the SSE endpoint and collect the first n_events (or until timeout)."""
    collected: list[dict] = []
    done = threading.Event()

    def _reader() -> None:
        req = urllib.request.Request(url)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=timeout + 1) as resp:
                buf = b""
                while not done.is_set() and len(collected) < n_events:
                    chunk = resp.read(1)
                    if not chunk:
                        break
                    buf += chunk
                    if buf.endswith(b"\n\n"):
                        for line in buf.decode().splitlines():
                            if line.startswith("data: "):
                                collected.append(json.loads(line[6:]))
                        buf = b""
                        if len(collected) >= n_events:
                            done.set()
        except Exception:
            pass

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    t.join(timeout)
    done.set()
    return collected


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


def run_contract(base_url: str, pair_code: str, assistant: FakeAssistant) -> list[str]:
    """Run the full mobile contract.  Returns list of failure messages (empty = all pass)."""
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        mark = "OK" if cond else "FAIL"
        extra = f"  — {detail}" if detail else ""
        print(f"  [{mark}] {name}{extra}")
        if not cond:
            failures.append(name)

    # --- 1. Reject requests without a token --------------------------------
    print("\n1. Auth rejection")
    status, _ = _get_json(f"{base_url}/events")
    check("GET /events without token → 401", status == 401)

    status, _ = _post(f"{base_url}/turn", {"text": "hello"})
    check("POST /turn without token → 401", status == 401)

    # --- 2. POST /pair: invalid code ----------------------------------------
    print("\n2. Pairing — invalid code")
    status, body = _post(f"{base_url}/pair", {"code": "ZZZZZZ", "device": "test"})
    check("POST /pair with wrong code → 403", status == 403, str(body))

    # --- 3. POST /pair: valid code → token ----------------------------------
    print("\n3. Pairing — valid code")
    status, body = _post(f"{base_url}/pair", {"code": pair_code, "device": "gate-client"})
    check("POST /pair with correct code → 200", status == 200, str(body))
    check("Response contains token", "token" in body)
    token: str = body.get("token", "")

    # --- 4. POST /turn: enqueue (interrupt=false) ----------------------------
    print("\n4. POST /turn — enqueue")
    before = len(assistant.turns)
    status, body = _post(f"{base_url}/turn", {"text": "hello world"}, token)
    check("POST /turn → 200", status == 200)
    check("submit_turn called", len(assistant.turns) == before + 1)
    turn = assistant.turns[-1] if assistant.turns else {}
    check("interrupt=False by default", turn.get("interrupt") is False)
    check("clear_queue=False by default", turn.get("clear_queue") is False)

    # --- 5. POST /turn: interrupt + clear_queue -----------------------------
    print("\n5. POST /turn — interrupt + clear_queue")
    status, body = _post(
        f"{base_url}/turn", {"text": "override", "interrupt": True, "clear_queue": True}, token
    )
    check("POST /turn interrupt → 200", status == 200)
    turn2 = assistant.turns[-1] if assistant.turns else {}
    check("interrupt=True forwarded", turn2.get("interrupt") is True)
    check("clear_queue=True forwarded", turn2.get("clear_queue") is True)

    # --- 6. POST /stop -------------------------------------------------------
    print("\n6. POST /stop")
    before_stops = assistant.stopped
    status, body = _post(f"{base_url}/stop", {}, token)
    check("POST /stop → 200", status == 200)
    check("stop() called on assistant", assistant.stopped == before_stops + 1)

    # --- 7. POST /confirm + /deny -------------------------------------------
    print("\n7. POST /confirm and /deny")
    status, body = _post(f"{base_url}/confirm", {"tool_call_id": "tc-42"}, token)
    check("POST /confirm → 200", status == 200)
    check("confirm() relayed with correct id", "tc-42" in assistant.confirmed)

    status, body = _post(f"{base_url}/deny", {"tool_call_id": "tc-99"}, token)
    check("POST /deny → 200", status == 200)
    check("deny() relayed with correct id", "tc-99" in assistant.denied)

    # --- 8. SSE stream + live event -----------------------------------------
    print("\n8. SSE stream — live events")

    def _emit_after_delay() -> None:
        time.sleep(0.15)
        assistant.bus.publish(TextDeltaEvent(delta="streamed!"))

    threading.Thread(target=_emit_after_delay, daemon=True).start()
    events = _collect_sse(f"{base_url}/events", token, n_events=1, timeout=2.0)
    check(
        "SSE delivers live TextDeltaEvent",
        len(events) >= 1 and events[0].get("type") == "text_delta",
    )

    # --- 9. SSE resume with since=N (replay) --------------------------------
    print("\n9. SSE resume — replay from since=N")
    # Publish 3 events to the bus before connecting
    assistant.bus.publish(DoneEvent(content="r1"))
    assistant.bus.publish(DoneEvent(content="r2"))
    assistant.bus.publish(DoneEvent(content="r3"))
    history_len = len(assistant.bus.history())
    # Connect with since=history_len-2 → should get exactly 2 replay events
    sse_url = f"{base_url}/events?since={history_len - 2}"
    replay_events = _collect_sse(sse_url, token, n_events=2, timeout=2.0)
    check(
        f"Replay delivers 2 events from since={history_len - 2}",
        len(replay_events) == 2,
        f"got {len(replay_events)}",
    )
    check(
        "Replay events are DoneEvents",
        all(e.get("type") == "done" for e in replay_events),
        str(replay_events),
    )

    # --- 10. POST /close_session --------------------------------------------
    print("\n10. POST /close_session")
    before_resets = assistant.sessions_reset
    status, body = _post(f"{base_url}/close_session", {}, token)
    check("POST /close_session → 200", status == 200)
    check("reset_session() called on assistant", assistant.sessions_reset == before_resets + 1)

    return failures


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Mirach HTTP contract gate")
    parser.add_argument(
        "--url", default=None, help="Base URL of a running daemon (skips mock server)"
    )
    parser.add_argument("--token", default=None, help="Device token (when using --url)")
    parser.add_argument(
        "--code", default=None, help="Pairing code (when using --url without --token)"
    )
    args = parser.parse_args()

    assistant = FakeAssistant()

    if args.url:
        base_url = args.url.rstrip("/")
        pair_code = args.code or ""
        if args.token:
            # Skip pairing step — inject the token directly into the assistant's
            # fake store so the contract tests can still run the /pair invalid-code check.
            print(f"Using supplied token against {base_url}")
        print(f"\nRunning mobile contract against {base_url}")
        failures = run_contract(base_url, pair_code, assistant)
    else:
        # Self-contained: spin up a test server with the FakeAssistant.
        with tempfile.TemporaryDirectory() as tmp:
            devices_path = Path(tmp) / "devices.json"
            srv = MirachServer(assistant, "127.0.0.1", 0, devices_path=devices_path)
            srv.start()
            _, port = srv.get_address()
            pair_code = srv._pair_code
            base_url = f"http://127.0.0.1:{port}"
            print(f"Test server: {base_url}  pair_code={pair_code}")
            time.sleep(0.05)  # let the server thread bind
            failures = run_contract(base_url, pair_code, assistant)

    print()
    if failures:
        print(f"FAILED ({len(failures)} scenario(s)):")
        for f in failures:
            print(f"  • {f}")
        sys.exit(1)
    else:
        print("All scenarios passed — mobile contract READY")


if __name__ == "__main__":
    main()
