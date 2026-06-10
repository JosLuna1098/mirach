"""LLM backend via OpenCode CLI with progressive user feedback.

Wraps the `opencode run` subprocess and provides:
  - Short beep when launching the query.
  - Spoken filler phrases repeated every FILLER_DELAY_SEC so the user hears
    signs of life during long queries.
  - Progressive feedback: different messages at 10s, 30s, and 60s thresholds.
  - Health check: detects if the subprocess dies before the timeout.
  - Interruptible: the running OpenCode process can be killed via interrupt().
  - Dynamic timeout: longer timeout (5 min) for coding-related queries.
  - Session persistence: session ID saved to disk so conversations survive
    daemon restarts within the idle timeout window.
"""

from __future__ import annotations

import json
import random
import re
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from mirach import config, i18n, notify
from mirach.logging_setup import log


@dataclass(slots=True)
class LLMResult:
    """Outcome of a single LLM query."""

    response: str  # cleaned text ready for TTS, or "" if interrupted
    new_session: bool  # was this the first turn of a fresh OpenCode session?
    interrupted: bool  # did the user abort mid-query?
    elapsed: float  # seconds spent waiting for OpenCode


@runtime_checkable
class LLMBackend(Protocol):
    """Structural protocol for LLM backends. Swap by passing a different adapter to Assistant."""

    def query(self, text: str, system_prompt: str, obsidian_context: str = "") -> LLMResult: ...
    def interrupt(self) -> None: ...
    def session_expired(self) -> bool: ...
    def reset_session(self) -> None: ...


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting so TTS reads naturally.

    Strips: bold/italic, code blocks, inline code, headers, links,
    tables, list markers, horizontal rules, and excessive whitespace.
    """
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"\|[-: ]+\|[-| :]*\n?", "", text)
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[-*_]{3,}$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _is_coding_query(text: str) -> bool:
    """Check if the query is likely a coding/programming task based on keyword matching."""
    lower = text.lower()
    return any(kw in lower for kw in config.CODING_KEYWORDS)


class OpenCodeBackend:
    """OpenCode CLI wrapper with session management and progressive feedback.

    Manages a session ID that persists across turns and across daemon restarts
    (saved to ~/.cache/mirach/session_id). A new session is started when the
    idle timeout expires.
    """

    def __init__(self, speak_filler: Callable[[str], None]) -> None:
        """`speak_filler` is the TTS function for playing short cached phrases."""
        self._speak_filler = speak_filler
        self._session_id: str | None = None
        self._last_interaction: float = 0.0
        self._proc: subprocess.Popen | None = None
        self._proc_lock = threading.Lock()
        self._interrupted = False
        self._load_session_id()

    def _load_session_id(self) -> None:
        """Restore persisted session ID from disk if the file exists."""
        if config.SESSION_ID_PATH.exists():
            try:
                cached = config.SESSION_ID_PATH.read_text().strip()
                if cached:
                    self._session_id = cached
                    self._last_interaction = config.SESSION_ID_PATH.stat().st_mtime
                    log.info("Restored session ID from cache: %s", cached[:8])
            except OSError:
                pass

    def _save_session_id(self) -> None:
        """Persist current session ID to disk for daemon restart survival."""
        if self._session_id:
            config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            config.SESSION_ID_PATH.write_text(self._session_id)

    @property
    def session_id(self) -> str | None:
        """Current OpenCode session ID, or None if no active session."""
        return self._session_id

    def session_expired(self) -> bool:
        """True if no session exists or the idle timeout has elapsed."""
        if self._session_id is None:
            return True
        return (time.time() - self._last_interaction) > config.SESSION_IDLE_TIMEOUT

    def reset_session(self) -> None:
        """Clear the current session ID and remove the persisted file."""
        self._session_id = None
        if config.SESSION_ID_PATH.exists():
            config.SESSION_ID_PATH.unlink(missing_ok=True)

    def interrupt(self) -> None:
        """Kill the running OpenCode subprocess if any."""
        with self._proc_lock:
            if self._proc is not None and self._proc.poll() is None:
                self._interrupted = True
                self._proc.terminate()
                log.info("LLM interrupted")

    def _start_filler_loop(
        self, proc: subprocess.Popen, stop_event: threading.Event, start_time: float
    ) -> threading.Thread:
        """Background thread that plays fillers and notifications while the LLM works.

        Time thresholds:
        - 0-10s: normal filler phrases
        - 10-30s: normal fillers + desktop notification at 10s
        - 30-60s: "still working" spoken message
        - 60s+: "complex query" message + desktop notification
        """

        def loop() -> None:
            phrases = i18n.fillers()
            notified_10s = False
            notified_60s = False
            while not stop_event.wait(config.FILLER_DELAY_SEC):
                elapsed = time.time() - start_time
                if proc.poll() is not None or stop_event.is_set():
                    return

                # Progressive feedback by elapsed time
                if elapsed >= 60 and not notified_60s:
                    notified_60s = True
                    notify.notify(
                        i18n.t("processing_title"),
                        i18n.t("complex_query"),
                        "dialog-information",
                    )
                    self._speak_filler(i18n.t("complex_query"))
                elif elapsed >= 30:
                    self._speak_filler(i18n.t("still_working"))
                elif elapsed >= 10 and not notified_10s:
                    notified_10s = True
                    notify.notify(
                        i18n.t("processing_title"),
                        i18n.t("processing_body"),
                        "dialog-information",
                    )
                    self._speak_filler(random.choice(phrases))
                else:
                    self._speak_filler(random.choice(phrases))

        t = threading.Thread(target=loop, daemon=True)
        t.start()
        return t

    def _execute(self, query: str, coding: bool) -> tuple[str | None, str | None]:
        """Run `opencode run` and parse the JSON-line output.

        Returns (response_text, new_session_id) or (None, None) on error/interrupt.
        Uses dynamic timeout based on whether the query is coding-related.
        """
        timeout = config.OPENCODE_TIMEOUT_CODING if coding else config.OPENCODE_TIMEOUT
        log.info("OpenCode timeout: %.0fs (coding=%s)", timeout, coding)

        # NOTE: --dangerously-skip-permissions grants the agent unattended tool
        # access. Voice is a semi-trusted input channel, so the guardrails live
        # in the Obsidian memory policy (e.g. "never format/wipe the machine")
        # rather than in interactive prompts. Declarative, harness-enforced
        # policy is tracked separately (future custom harness).
        cmd = [
            "opencode",
            "run",
            "--model",
            config.OPENCODE_MODEL,
            "--format",
            "json",
            "--dangerously-skip-permissions",
        ]
        if self._session_id:
            cmd += ["--session", self._session_id]
        cmd.append(query)

        with self._proc_lock:
            self._interrupted = False
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            proc = self._proc

        notify.play_beep(config.BEEP_PROCESS_WAV)

        stop_filler = threading.Event()
        start_time = time.time()
        filler_thread = self._start_filler_loop(proc, stop_filler, start_time)

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stop_filler.set()
            raise
        finally:
            stop_filler.set()
            filler_thread.join(timeout=1)
            with self._proc_lock:
                self._proc = None

        if self._interrupted:
            return None, None

        if proc.returncode != 0 and not stdout.strip():
            log.error("OpenCode rc=%d: %s", proc.returncode, stderr[:120])
            return None, None

        # Parse JSON-line output: extract session ID and text events
        parts: list[str] = []
        new_id = self._session_id
        for line in stdout.strip().split("\n"):
            if not line:
                continue
            try:
                event = json.loads(line)
                if not new_id and event.get("sessionID"):
                    new_id = event["sessionID"]
                if event.get("type") == "text":
                    parts.append(event["part"]["text"])
            except json.JSONDecodeError:
                pass

        return " ".join(parts).strip(), new_id

    def query(self, text: str, system_prompt: str, obsidian_context: str = "") -> LLMResult:
        """Run a single LLM turn. Returns LLMResult with interrupted=True if aborted.

        On a new session, the system prompt and optional Obsidian context are
        prepended to the query text (OpenCode has no --system flag).
        """
        t0 = time.time()
        new_session = self.session_expired()
        if new_session:
            self.reset_session()

        # Determine timeout category once based on user query
        coding = _is_coding_query(text)

        # Build query payload. On a new session we prepend the system prompt
        # and/or the restored Obsidian context (each optional, injected
        # independently); subsequent turns send the raw text.
        if new_session and (system_prompt or obsidian_context):
            blocks: list[str] = []
            if system_prompt:
                blocks.append(
                    f"Follow these instructions for the ENTIRE conversation:\n\n{system_prompt}"
                )
            if obsidian_context:
                blocks.append(f"Restored context from your memory:\n\n{obsidian_context}")
            preamble = "\n\n---\n\n".join(blocks)
            payload = f"{preamble}\n\n---\n\nFirst query: {text}"
            log.info(
                "New OpenCode session — injected %s",
                ", ".join(
                    p
                    for p, ok in [("system prompt", system_prompt), ("memory", obsidian_context)]
                    if ok
                ),
            )
        else:
            payload = text

        log.info(
            "OpenCode %s",
            f"session {self._session_id[:8]}" if self._session_id else "new session",
        )

        try:
            response, new_id = self._execute(payload, coding)
        except subprocess.TimeoutExpired:
            timeout_label = config.OPENCODE_TIMEOUT_CODING if coding else config.OPENCODE_TIMEOUT
            log.error("OpenCode timeout (%.0fs)", timeout_label)
            return LLMResult(i18n.t("timeout_error"), new_session, False, time.time() - t0)
        except Exception as e:
            log.exception("OpenCode error: %s", e)
            return LLMResult(i18n.t("generic_error"), new_session, False, time.time() - t0)

        if self._interrupted:
            return LLMResult("", new_session, True, time.time() - t0)

        if not response:
            log.warning("OpenCode: empty response")
            return LLMResult(i18n.t("no_response"), new_session, False, time.time() - t0)

        # Update session tracking
        if new_id and new_id != self._session_id:
            self._session_id = new_id
            self._save_session_id()
            log.info("Session ID: %s", self._session_id)

        self._last_interaction = time.time()
        response = _strip_markdown(response)
        elapsed = time.time() - t0
        log.info("OpenCode responded (%.2fs): %s", elapsed, response[:120])
        return LLMResult(response, new_session, False, elapsed)
