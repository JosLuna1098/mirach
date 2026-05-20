"""Top-level orchestrator. Owns the FSM (IDLE → RECORDING → PROCESSING).

Pressing the hotkey while PROCESSING interrupts the current pipeline
(stops TTS / kills the LLM call) and immediately starts a new recording.
"""

from __future__ import annotations

import atexit
import contextlib
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from mirach import config, i18n, notify
from mirach.audio import AudioRecorder
from mirach.conversation import ConversationLog
from mirach.ipc import SocketServer
from mirach.llm import LLMBackend, OpenCodeBackend
from mirach.logging_setup import log
from mirach.obsidian_cache import ObsidianCache
from mirach.stt import WhisperTranscriber
from mirach.tts import PiperSpeaker


class State(Enum):
    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()


class _Interrupted(Exception):
    """Raised by the pipeline when the user aborts the current run."""


@dataclass
class UserScript:
    """A user-defined voice-triggered script."""

    path: Path
    triggers: list[str]
    response: str
    description: str = ""


class Assistant:
    def __init__(
        self,
        *,
        audio: AudioRecorder | None = None,
        stt: WhisperTranscriber | None = None,
        tts: PiperSpeaker | None = None,
        llm: LLMBackend | None = None,
    ) -> None:
        self._state = State.IDLE
        self._state_lock = threading.Lock()
        self._interrupt = threading.Event()
        self._idle = threading.Event()
        self._idle.set()

        self._tts = tts or PiperSpeaker()
        self._audio = audio or AudioRecorder()
        self._stt = stt or WhisperTranscriber()
        self._llm = llm or OpenCodeBackend(speak_filler=self._tts.speak_filler)
        self._conv = ConversationLog()
        self._system_prompt = ""
        self._obsidian = ObsidianCache(config.OBSIDIAN_VAULT)
        self._user_scripts: list[UserScript] = []

    # --- State helpers ---
    def _set_state(self, new: State) -> None:
        with self._state_lock:
            self._state = new
        if new is State.IDLE:
            self._idle.set()
        else:
            self._idle.clear()

    def _check_interrupted(self) -> None:
        if self._interrupt.is_set():
            raise _Interrupted()

    # --- Initialization ---
    def load(self) -> None:
        self._stt.load()
        self._tts.load()
        self._audio.detect_microphone()
        if config.SYSTEM_PROMPT_PATH.exists():
            self._system_prompt = config.SYSTEM_PROMPT_PATH.read_text()
            log.info("System prompt loaded (%d chars)", len(self._system_prompt))
        else:
            log.warning(
                "System prompt %s not found — assistant will run without instructions",
                config.SYSTEM_PROMPT_PATH,
            )
        self._user_scripts = self._load_user_scripts()
        log.info("Loaded %d user scripts", len(self._user_scripts))
        # Warmup + filler cache so the first real turn is full speed.
        self._stt.warmup()
        self._tts.prebake_fillers(i18n.fillers())

    # --- User scripts ---
    @staticmethod
    def _parse_script_metadata(path: Path) -> UserScript | None:
        """Parse # triggers: and # response: from the first lines of a script."""
        triggers: list[str] = []
        response = ""
        description = ""

        with open(path) as f:
            for line in f:
                if line.startswith("#!"):
                    continue
                if not line.startswith("#"):
                    break
                m_triggers = re.match(r"#\s*triggers:\s*(.+)", line, re.IGNORECASE)
                m_response = re.match(r"#\s*response:\s*(.+)", line, re.IGNORECASE)
                m_desc = re.match(r"#\s*description:\s*(.+)", line, re.IGNORECASE)
                if m_triggers:
                    triggers = [t.strip().lower() for t in m_triggers.group(1).split(",")]
                elif m_response:
                    response = m_response.group(1).strip()
                elif m_desc:
                    description = m_desc.group(1).strip()

        if not triggers or not response:
            log.warning("Skipping %s: missing triggers or response", path.name)
            return None

        return UserScript(path=path, triggers=triggers, response=response, description=description)

    def _load_user_scripts(self) -> list[UserScript]:
        """Scan user_scripts/ directory and parse all valid scripts."""
        scripts_dir = config.BASE_DIR / "user_scripts"
        if not scripts_dir.is_dir():
            return []

        scripts: list[UserScript] = []
        for entry in sorted(scripts_dir.iterdir()):
            if entry.suffix in (".sh", ".py") and entry.name != ".gitkeep":
                parsed = self._parse_script_metadata(entry)
                if parsed:
                    scripts.append(parsed)
        return scripts

    def _match_user_script(self, text: str) -> UserScript | None:
        """Check if transcribed text matches any user script trigger."""
        lower = text.lower()
        for script in self._user_scripts:
            for trigger in script.triggers:
                if trigger in lower:
                    return script
        return None

    # --- Main pipeline ---
    def _process(self) -> None:
        started = time.time()
        try:
            audio = self._audio.stop()
            if audio is None or len(audio) < config.SAMPLE_RATE * 0.5:
                log.info("Empty or too-short audio")
                self._tts.speak(i18n.t("nothing_recorded"))
                return

            self._check_interrupted()
            notify.notify(i18n.t("processing_title"), i18n.t("processing_body"), "microphone")
            text = self._stt.transcribe(audio)
            if not text:
                self._tts.speak(i18n.t("didnt_hear"))
                return

            self._check_interrupted()
            notify.notify(i18n.t("you_said"), text)

            matched = self._match_user_script(text)
            if matched:
                log.info("User script triggered: %s", matched.path.name)
                subprocess.Popen(
                    [str(matched.path)],
                    start_new_session=True,
                )
                self._tts.speak(matched.response)
                self._conv.append(i18n.t("assistant"), matched.response)
                return

            new_session = self._llm.session_expired()
            if new_session:
                self._conv.start()
                self._obsidian.refresh()
            self._conv.append(i18n.t("you_said").rstrip(":"), text)

            obsidian_context = self._obsidian.get_context() if new_session else ""
            result = self._llm.query(text, self._system_prompt, obsidian_context)
            self._check_interrupted()
            if result.interrupted:
                return
            if not result.response:
                self._tts.speak(i18n.t("didnt_understand"))
                return

            self._conv.append(i18n.t("assistant"), result.response)
            notify.notify(i18n.t("assistant"), result.response)
            self._tts.speak(result.response)
            log.info("Pipeline complete in %.2fs", time.time() - started)
        except _Interrupted:
            log.info("Pipeline interrupted by user")
        except Exception as e:
            log.exception("Pipeline ERROR: %s", e)
            with contextlib.suppress(Exception):
                self._tts.speak(i18n.t("error_occurred"))
        finally:
            self._set_state(State.IDLE)

    # --- FSM: toggle ---
    def toggle(self) -> None:
        with self._state_lock:
            current = self._state

        if current is State.PROCESSING:
            # User wants to interrupt and start a new recording.
            log.info("User interrupt requested")
            self._interrupt.set()
            self._llm.interrupt()
            self._tts.interrupt()
            # Wait for the running pipeline to release the state.
            if not self._idle.wait(timeout=3.0):
                log.warning("Pipeline did not release in 3s, forcing IDLE")
                self._set_state(State.IDLE)
            self._interrupt.clear()
            current = State.IDLE  # fall through to start recording

        if current is State.IDLE:
            self._set_state(State.RECORDING)
            notify.play_beep(config.BEEP_START_WAV)
            self._audio.start()
            notify.notify(
                i18n.t("recording_start_title"),
                i18n.t("recording_start_body"),
                "microphone-sensitivity-high",
            )
        elif current is State.RECORDING:
            self._set_state(State.PROCESSING)
            threading.Thread(target=self._process, daemon=True).start()

    # --- Entry point ---
    def run(self) -> None:
        log.info("=== Daemon starting ===")
        notify.generate_beeps()
        _install_shutdown_hooks()
        self.load()
        notify.notify(i18n.t("daemon_ready_title"), i18n.t("daemon_ready_body"))
        SocketServer(on_toggle=self.toggle).serve_forever()


# --- Shutdown handling ---
_shutdown_played = False


def _play_shutdown_beep() -> None:
    """Audible signal that the daemon is going down. Safe to call multiple times."""
    global _shutdown_played
    if _shutdown_played:
        return
    _shutdown_played = True
    try:
        notify.play_beep(config.BEEP_SHUTDOWN_WAV, blocking=True)
        log.info("=== Daemon stopped ===")
    except Exception:
        pass


def _signal_handler(signum: int, frame) -> None:
    log.warning("Received signal %d, shutting down", signum)
    _play_shutdown_beep()
    sys.exit(0)


def _install_shutdown_hooks() -> None:
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    atexit.register(_play_shutdown_beep)


def main() -> None:
    Assistant().run()


if __name__ == "__main__":
    main()
