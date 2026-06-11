#!/usr/bin/env python3
"""Standalone opencode-serve probe — mirrors exactly what the Mirach daemon does
(open SSE /event, prompt_async, read deltas, wait for session.idle), but prints
every event with timing so you can SEE rate-limits/retries/errors in the open.

Usage
-----
  # 1) In one terminal, start a server WITH visible logs:
  #    cd ~/Projects/mirach
  #    opencode serve --hostname=127.0.0.1 --port=7410 --print-logs --log-level INFO 2>&1 | tee /tmp/oc.log
  #
  # 2) In another terminal, fire prompts at it (run it a few times in a row):
  #    venv/bin/python tools/oc_probe.py "¿Cuánto es 4 más 4?"
  #
  # Knobs (env vars):
  #    OC_URL    server base URL   (default http://127.0.0.1:7410)
  #    OC_MODEL  provider/model    (default google/gemini-2.5-flash; "" = server default)
  #    OC_CWD    directory param   (default current dir)
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
from urllib.parse import urlencode

BASE = os.environ.get("OC_URL", "http://127.0.0.1:7410").rstrip("/")
MODEL = os.environ.get("OC_MODEL", "google/gemini-2.5-flash")
CWD = os.environ.get("OC_CWD", os.getcwd())


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=400) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def main() -> None:
    prompt = sys.argv[1] if len(sys.argv) > 1 else "¿Cuánto es 4 más 4?"
    q = "?" + urlencode({"directory": CWD})

    sid = _post("/session", {})["id"]
    print(f"session: {sid}  model: {MODEL or '(server default)'}")

    body: dict = {"parts": [{"type": "text", "text": prompt}]}
    if MODEL:
        provider, _, model = MODEL.partition("/")
        body["model"] = {"providerID": provider, "modelID": model}

    t0 = time.time()
    sse_req = urllib.request.Request(f"{BASE}/event{q}", headers={"Accept": "text/event-stream"})
    sse = urllib.request.urlopen(sse_req, timeout=400)

    def _prompt() -> None:
        time.sleep(0.3)
        _post(f"/session/{sid}/prompt_async{q}", body)

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
        et = ev.get("type")
        props = ev.get("properties", {})
        if et == "message.part.delta" and props.get("field") == "text":
            text += props.get("delta", "")
        elif et == "session.error":
            print(f"  +{time.time() - t0:5.1f}s  *** session.error: {props.get('error')}")
        elif et == "session.idle" and props.get("sessionID", sid) == sid:
            print(f"  +{time.time() - t0:5.1f}s  session.idle (done)")
            break
        else:
            print(f"  +{time.time() - t0:5.1f}s  {et}")

    print(f"\nelapsed: {time.time() - t0:.1f}s")
    print(f"response: {text!r}")


if __name__ == "__main__":
    main()
