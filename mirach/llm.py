"""LLM backend via OpenCode CLI.

Wraps the subprocess and the user-facing feedback while the model works:
- short beep when launching
- spoken filler **repeated** every FILLER_DELAY_SEC, so the user keeps hearing
  signs of life on long queries
- interruptible: the running OpenCode process can be killed via interrupt()
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
    elapsed: float  # seconds spent in OpenCode


@runtime_checkable
class LLMBackend(Protocol):
    """Structural protocol for LLM backends. Swap by passing a different adapter to Assistant."""

    def query(self, text: str, system_prompt: str) -> LLMResult: ...
    def interrupt(self) -> None: ...
    def session_expired(self) -> bool: ...
    def reset_session(self) -> None: ...


def _strip_markdown(text: str) -> str:
    """Strip markdown so TTS reads naturally."""
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


class OpenCodeBackend:
    def __init__(self, speak_filler: Callable[[str], None]) -> None:
        """`speak_filler` is the TTS function for short cached phrases."""
        self._speak_filler = speak_filler
        self._session_id: str | None = None
        self._last_interaction: float = 0.0
        self._proc: subprocess.Popen | None = None
        self._proc_lock = threading.Lock()
        self._interrupted = False
        self._load_session_id()

    def _load_session_id(self) -> None:
        """Restore persisted session ID from disk if still valid."""
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
        """Persist current session ID to disk."""
        if self._session_id:
            config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            config.SESSION_ID_PATH.write_text(self._session_id)

    @property
    def session_id(self) -> str | None:
        return self._session_id

    def session_expired(self) -> bool:
        if self._session_id is None:
            return True
        return (time.time() - self._last_interaction) > config.SESSION_IDLE_TIMEOUT

    def reset_session(self) -> None:
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
        self, proc: subprocess.Popen, stop_event: threading.Event
    ) -> threading.Thread:
        """Background thread that speaks a filler every FILLER_DELAY_SEC while proc runs."""

        def loop() -> None:
            phrases = i18n.fillers()
            while not stop_event.wait(config.FILLER_DELAY_SEC):
                if proc.poll() is not None or stop_event.is_set():
                    return
                self._speak_filler(random.choice(phrases))

        t = threading.Thread(target=loop, daemon=True)
        t.start()
        return t

    def _execute(self, query: str) -> tuple[str | None, str | None]:
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
        filler_thread = self._start_filler_loop(proc, stop_filler)

        try:
            stdout, stderr = proc.communicate(timeout=config.OPENCODE_TIMEOUT)
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

    def query(self, text: str, system_prompt: str) -> LLMResult:
        """Run a single LLM turn. Returns LLMResult with `interrupted=True` if aborted."""
        t0 = time.time()
        new_session = self.session_expired()
        if new_session:
            self.reset_session()

        if new_session and system_prompt:
            payload = (
                "Actúa según estas instrucciones para TODA esta conversación:\n\n"
                f"{system_prompt}\n\n---\n\nPrimera consulta: {text}"
            )
            log.info("New OpenCode session — system prompt injected")
        else:
            payload = text

        log.info(
            "OpenCode %s",
            f"session {self._session_id[:8]}" if self._session_id else "new session",
        )

        try:
            response, new_id = self._execute(payload)
        except subprocess.TimeoutExpired:
            log.error("OpenCode timeout (%.0fs)", config.OPENCODE_TIMEOUT)
            return LLMResult(i18n.t("timeout_error"), new_session, False, time.time() - t0)
        except Exception as e:
            log.exception("OpenCode error: %s", e)
            return LLMResult(i18n.t("generic_error"), new_session, False, time.time() - t0)

        if self._interrupted:
            return LLMResult("", new_session, True, time.time() - t0)

        if not response:
            log.warning("OpenCode: empty response")
            return LLMResult(i18n.t("no_response"), new_session, False, time.time() - t0)

        if new_id and new_id != self._session_id:
            self._session_id = new_id
            self._save_session_id()
            log.info("Session ID: %s", self._session_id)

        self._last_interaction = time.time()
        response = _strip_markdown(response)
        elapsed = time.time() - t0
        log.info("OpenCode responded (%.2fs): %s", elapsed, response[:120])
        return LLMResult(response, new_session, False, elapsed)
