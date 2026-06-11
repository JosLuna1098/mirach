"""NativeBackend — LLMBackend adapter wrapping AgentLoop for the voice pipeline."""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from mirach import config, i18n
from mirach.llm_types import LLMResult, _strip_markdown
from mirach.logging_setup import log

if TYPE_CHECKING:
    from mirach.harness.loop import AgentLoop


class NativeBackend:
    """
    Drop-in replacement for OpenCodeBackend that routes queries through AgentLoop.

    Session semantics mirror OpenCodeBackend: idle timeout reuses
    config.SESSION_IDLE_TIMEOUT. History is in-memory only (no disk persistence).
    System prompt is injected on every turn; obsidian context is only appended
    on the first turn of each new session.
    """

    def __init__(
        self,
        loop: AgentLoop,
        speak_filler: Callable[[str], None] | None = None,
    ) -> None:
        self._loop = loop
        self._speak_filler = speak_filler
        self._interrupt = threading.Event()
        self._last_interaction: float = 0.0

    # ── LLMBackend protocol ───────────────────────────────────────────────────

    @property
    def bus(self):
        """The AgentLoop's ConversationBus (shared with the daemon's server)."""
        return self._loop.bus

    def confirm(self, tool_call_id: str) -> None:
        """Approve a mid-flight tool confirmation (from the IPC/server thread)."""
        self._loop.confirm(tool_call_id)

    def deny(self, tool_call_id: str) -> None:
        """Reject a mid-flight tool confirmation (from the IPC/server thread)."""
        self._loop.deny(tool_call_id)

    def query(self, text: str, system_prompt: str, obsidian_context: str = "") -> LLMResult:
        t0 = time.time()
        new_session = self.session_expired()
        if new_session:
            self.reset_session()

        self._interrupt.clear()

        # Build the system prompt for this turn.
        # Obsidian context is only injected on the first turn of a new session
        # (the model has it in history afterwards).
        effective_system = _build_system(system_prompt, obsidian_context if new_session else "")
        if new_session and effective_system:
            log.info(
                "Native backend: new session — injected %s",
                ", ".join(
                    p
                    for p, ok in [("system prompt", system_prompt), ("memory", obsidian_context)]
                    if ok
                ),
            )

        stop_filler = threading.Event()
        if self._speak_filler:
            filler_thread = self._start_filler_loop(stop_filler)

        try:
            result_text = self._loop.run(
                text,
                interrupt=self._interrupt,
                system_prompt=effective_system,
            )
        except Exception as exc:
            log.exception("Native backend error: %s", exc)
            return LLMResult(i18n.t("generic_error"), new_session, False, time.time() - t0)
        finally:
            stop_filler.set()
            if self._speak_filler:
                filler_thread.join(timeout=1)

        interrupted = self._interrupt.is_set() and not result_text
        if interrupted:
            return LLMResult("", new_session, True, time.time() - t0)

        if not result_text:
            log.warning("Native backend: empty response")
            return LLMResult(i18n.t("no_response"), new_session, False, time.time() - t0)

        self._last_interaction = time.time()
        response = _strip_markdown(result_text)
        elapsed = time.time() - t0
        log.info("Native backend responded (%.2fs): %s", elapsed, response[:120])
        return LLMResult(response, new_session, False, elapsed)

    def interrupt(self) -> None:
        self._interrupt.set()
        log.info("Native backend interrupted")

    def session_expired(self) -> bool:
        if self._last_interaction == 0.0:
            return True
        return (time.time() - self._last_interaction) > config.SESSION_IDLE_TIMEOUT

    def reset_session(self) -> None:
        self._loop.reset()
        self._last_interaction = 0.0

    # ── private ───────────────────────────────────────────────────────────────

    def _start_filler_loop(self, stop_event: threading.Event) -> threading.Thread:
        def loop() -> None:
            phrases = i18n.fillers()
            while not stop_event.wait(config.FILLER_DELAY_SEC):
                if stop_event.is_set():
                    return
                self._speak_filler(random.choice(phrases))  # type: ignore[misc]

        t = threading.Thread(target=loop, daemon=True)
        t.start()
        return t


# ── helpers ───────────────────────────────────────────────────────────────────


def _build_system(system_prompt: str, obsidian_context: str) -> str:
    """Combine system prompt and obsidian context into a single system message."""
    blocks: list[str] = []
    if system_prompt:
        blocks.append(f"Follow these instructions for the ENTIRE conversation:\n\n{system_prompt}")
    if obsidian_context:
        blocks.append(f"Restored context from your memory:\n\n{obsidian_context}")
    return "\n\n---\n\n".join(blocks)
