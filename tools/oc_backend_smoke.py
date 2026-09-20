#!/usr/bin/env python3
"""Integration smoke for OpenCodeServeBackend against a real opencode 2.x server.

Unlike tests/, this spawns an actual `opencode serve` child through the backend
itself and drives four scenarios end to end:

  (a) plain question + system prompt (checks the instruction entry took)
  (b) a shell command → permission → ToolCallEvent / ToolResultEvent
  (c) a long turn interrupted mid-flight, then an immediate follow-up
  (d) reset_session() + stop(), and the child really exited

Usage
-----
  SB=~/.cache/mirach-oc2-sandbox
  env XDG_DATA_HOME=$SB/data XDG_CONFIG_HOME=$SB/config XDG_CACHE_HOME=$SB/cache \\
      XDG_STATE_HOME=$SB/state MIRACH_OPENCODE_BIN=$SB/pkg/usr/bin/opencode \\
      venv/bin/python tools/oc_backend_smoke.py

Do NOT set OPENCODE_PASSWORD: the backend generates one per process.
"""

from __future__ import annotations

import os
import sys
import threading
import time

from mirach import config
from mirach.harness.events import AwaitingConfirmationEvent, ConversationBus
from mirach.harness.policy.engine import PolicyEngine
from mirach.harness.providers.opencode import OpenCodeServeBackend

SANDBOX_WORK = os.environ.get(
    "OC_SMOKE_CWD", os.path.expanduser("~/.cache/mirach-oc2-sandbox/work")
)
PROVIDER_ID = os.environ.get("OC_SMOKE_PROVIDER", "opencode")
MODEL_ID = os.environ.get("OC_SMOKE_MODEL", "big-pickle")


def main() -> int:
    bus = ConversationBus()
    events: list[object] = []

    def _record(ev: object) -> None:
        events.append(ev)
        payload = ev.to_dict() if hasattr(ev, "to_dict") else ev
        print(f"    [bus] {type(ev).__name__}: {str(payload)[:200]}")

    bus.subscribe(_record)

    backend = OpenCodeServeBackend(
        policy=PolicyEngine.load(config.NATIVE_POLICY_PATH),
        bus=bus,
        provider_id=PROVIDER_ID,
        model_id=MODEL_ID,
        cwd=SANDBOX_WORK,
    )

    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}{': ' + detail if detail else ''}")
        if not ok:
            failures.append(label)

    print(f"starting opencode serve ({config.OPENCODE_BIN}) ...")
    backend.start()
    print(f"  base_url = {backend._base_url}")

    try:
        # ── (a) plain question with a system prompt ──────────────────────────
        print("\n(a) plain question")
        events.clear()
        result = backend.query(
            "¿Cuánto es 4 más 4?",
            system_prompt=(
                "Responde siempre en una sola frase y termina con la palabra ZANAHORIA."
            ),
        )
        print(f"    response: {result.response!r}")
        check("(a) non-empty response", bool(result.response.strip()))
        check(
            "(a) instruction entry honoured",
            "ZANAHORIA" in result.response.upper(),
            result.response[:80],
        )

        # ── (b) shell command through the policy ─────────────────────────────
        print("\n(b) shell command")
        events.clear()
        confirmed: list[str] = []

        def _auto_confirm() -> None:
            seen: set[int] = set()
            deadline = time.time() + 120
            while time.time() < deadline:
                for ev in list(events):
                    if isinstance(ev, AwaitingConfirmationEvent) and id(ev) not in seen:
                        seen.add(id(ev))
                        confirmed.append(ev.tool_call_id)
                        print(f"    >>> confirming {ev.name} {ev.arguments}")
                        backend.confirm(ev.tool_call_id)
                time.sleep(0.05)

        threading.Thread(target=_auto_confirm, daemon=True).start()
        result = backend.query("Ejecuta el comando: echo hola-mirach", system_prompt="")
        names = [type(e).__name__ for e in events]
        tool_results = [e for e in events if type(e).__name__ == "ToolResultEvent"]
        print(f"    response: {result.response!r}")
        print(f"    path: {'CONFIRM' if confirmed else 'ALLOW (policy decided directly)'}")
        check("(b) ToolCallEvent published", "ToolCallEvent" in names)
        check("(b) ToolResultEvent published", bool(tool_results))
        check(
            "(b) command actually ran",
            any("hola-mirach" in (e.result or "") for e in tool_results),
            "; ".join((e.result or "")[:60] for e in tool_results),
        )

        # ── (c) interrupt, then an immediate follow-up ───────────────────────
        print("\n(c) interrupt")
        events.clear()

        def _interrupt_later() -> None:
            time.sleep(2.0)
            print("    >>> interrupt()")
            backend.interrupt()

        threading.Thread(target=_interrupt_later, daemon=True).start()
        result = backend.query(
            "Cuenta del 1 al 200 despacio, un número por línea.", system_prompt=""
        )
        check("(c) result marked interrupted", result.interrupted is True, repr(result.response))

        print("    follow-up query")
        result = backend.query("¿Cuánto es 2 más 2? Responde solo el número.", system_prompt="")
        check(
            "(c) follow-up completes normally",
            not result.interrupted and bool(result.response.strip()),
            result.response[:80],
        )

        # ── (d) teardown ─────────────────────────────────────────────────────
        print("\n(d) teardown")
        proc = backend._proc
        backend.reset_session()
        check("(d) session cleared", backend._session_id is None)
        backend.stop()
        time.sleep(0.5)
        check("(d) child process exited", proc is not None and proc.poll() is not None)

    finally:
        backend.stop()

    print()
    if failures:
        print(f"SMOKE FAILED ({len(failures)}): {', '.join(failures)}")
        return 1
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
