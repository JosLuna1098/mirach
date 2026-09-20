#!/usr/bin/env python3
"""Standalone opencode-serve probe (API v2) — mirrors exactly what the Mirach
daemon does (open SSE /api/event, POST the prompt, read text deltas, wait for a
terminal session.execution.* event), but prints every event with timing so you
can SEE rate-limits/retries/permissions/errors in the open.

Usage
-----
  # 1) In one terminal, start a server WITH visible logs:
  #    cd ~/Projects/mirach
  #    OPENCODE_PASSWORD=pw opencode serve --hostname=127.0.0.1 --port=7411 --print-logs 2>&1 | tee /tmp/oc.log
  #
  # 2) In another terminal, fire prompts at it (run it a few times in a row):
  #    OC_PASSWORD=pw venv/bin/python tools/oc_probe.py "¿Cuánto es 4 más 4?"
  #
  # Knobs (env vars):
  #    OC_URL       server base URL  (default http://127.0.0.1:7411)
  #    OC_PASSWORD  server password  (required; same as OPENCODE_PASSWORD)
  #    OC_MODEL     provider/model   (default opencode/big-pickle; "" = server default)
  #    OC_CWD       session directory (default current dir)
"""

from __future__ import annotations

import base64
import json
import os
import sys
import threading
import time
import urllib.request
from urllib.parse import quote

BASE = os.environ.get("OC_URL", "http://127.0.0.1:7411").rstrip("/")
PASSWORD = os.environ.get("OC_PASSWORD", "")
MODEL = os.environ.get("OC_MODEL", "opencode/big-pickle")
CWD = os.environ.get("OC_CWD", os.getcwd())

_API = "/api"


def _headers(*, json_body: bool = False, sse: bool = False) -> dict[str, str]:
    token = base64.b64encode(f"opencode:{PASSWORD}".encode()).decode()
    h = {"Authorization": f"Basic {token}", "x-opencode-directory": quote(CWD)}
    if json_body:
        h["Content-Type"] = "application/json"
    if sse:
        h["Accept"] = "text/event-stream"
    return h


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        BASE + _API + path,
        data=json.dumps(body).encode(),
        headers=_headers(json_body=True),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=400) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def main() -> None:
    if not PASSWORD:
        sys.exit("OC_PASSWORD is required (the server's OPENCODE_PASSWORD)")

    prompt = sys.argv[1] if len(sys.argv) > 1 else "¿Cuánto es 4 más 4?"

    body: dict = {"location": {"directory": CWD}}
    if MODEL:
        provider, _, model = MODEL.partition("/")
        body["model"] = {"providerID": provider, "id": model}

    sid = _post("/session", body)["data"]["id"]
    print(f"session: {sid}  model: {MODEL or '(server default)'}")

    t0 = time.time()
    sse_req = urllib.request.Request(f"{BASE}{_API}/event", headers=_headers(sse=True))
    sse = urllib.request.urlopen(sse_req, timeout=400)

    def _prompt() -> None:
        time.sleep(0.3)
        _post(f"/session/{sid}/prompt", {"text": prompt})

    threading.Thread(target=_prompt, daemon=True).start()

    text = ""
    while time.time() - t0 < 400:
        line = sse.readline()
        if not line:
            break
        if not line.startswith(b"data:"):
            continue
        try:
            ev = json.loads(line[5:].strip())
        except json.JSONDecodeError:
            continue
        et = ev.get("type") or ""
        data = ev.get("data") or {}
        print(f"  +{time.time() - t0:5.1f}s  {et}")
        if et in ("permission.asked", "session.execution.failed", "form.created"):
            print(f"           {json.dumps(data, ensure_ascii=False)}")
        if data.get("sessionID") != sid:
            continue
        if et == "session.text.delta":
            text += data.get("delta", "")
        elif et in (
            "session.execution.succeeded",
            "session.execution.failed",
            "session.execution.interrupted",
        ):
            break

    print(f"\nelapsed: {time.time() - t0:.1f}s")
    print(f"response: {text!r}")


if __name__ == "__main__":
    main()
