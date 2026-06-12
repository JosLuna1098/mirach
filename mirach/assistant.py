"""Top-level orchestrator for the Mirach voice assistant.

Owns a three-state finite state machine: IDLE → RECORDING → PROCESSING → IDLE.
The only entry point is toggle(), called by the Unix socket server on every
"toggle" message from the hotkey trigger.

When PROCESSING, a second toggle() interrupts the running pipeline (kills the
LLM subprocess and aborts TTS playback), then immediately starts a new recording.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import re
import signal
import stat
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from mirach import config, i18n, notify
from mirach.audio import AudioRecorder
from mirach.conversation import ConversationLog
from mirach.conversation_html import generate_and_open as show_conversation_html
from mirach.ipc import SocketServer
from mirach.llm_types import LLMBackend
from mirach.logging_setup import log
from mirach.obsidian_cache import ObsidianCache
from mirach.stt import WhisperTranscriber
from mirach.tts import PiperSpeaker


class State(Enum):
    """FSM states for the assistant pipeline."""

    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()


class _Interrupted(Exception):
    """Raised internally to unwind the pipeline when the user aborts the current run."""


# Max text turns that may wait in the queue before new ones are rejected.
MAX_QUEUE = 10


@dataclass
class UserScript:
    """A user-defined voice-triggered script parsed from user_scripts/."""

    path: Path
    triggers: list[str]
    response: str
    description: str = ""


@dataclass
class _PendingConfirm:
    """A tool confirmation a voice turn is answering by voice (spoken Q + hotkey A)."""

    tool_call_id: str
    timer: threading.Timer
    recording: bool = False


# Words that count as a "yes" when interpreting a spoken confirmation answer (ES + EN).
# Anything without one of these is treated as "no" — unclear answers fail safe to deny.
_AFFIRMATIVE_WORDS = frozenset(
    {
        "sí",
        "si",
        "claro",
        "dale",
        "ok",
        "okay",
        "vale",
        "confirmo",
        "confirmado",
        "adelante",
        "hazlo",
        "correcto",
        "afirmativo",
        "bueno",
        "perfecto",
        "yes",
        "yeah",
        "yep",
        "yup",
        "sure",
        "confirm",
        "confirmed",
        "go",
        "do",
    }
)


# Built-in trigger phrases that bypass the LLM entirely.
# Keys are lowercase trigger phrases, values are (i18n response key, handler name).
BUILTIN_TRIGGERS: dict[str, tuple[str, str]] = {
    # Show conversation — Spanish variants
    "muéstrame la conversación": ("conversation_shown", "conversation"),
    "ver conversación": ("conversation_shown", "conversation"),
    "muestra la conversación": ("conversation_shown", "conversation"),
    "lee la conversación": ("conversation_shown", "conversation"),
    "ver la conversación": ("conversation_shown", "conversation"),
    "mostrar conversación": ("conversation_shown", "conversation"),
    # Show conversation — English variants
    "show conversation": ("conversation_shown", "conversation"),
    "show the conversation": ("conversation_shown", "conversation"),
    "read conversation": ("conversation_shown", "conversation"),
    "read the conversation": ("conversation_shown", "conversation"),
    "view conversation": ("conversation_shown", "conversation"),
    "view the conversation": ("conversation_shown", "conversation"),
}


class Assistant:
    """Main assistant orchestrator. Manages the FSM and owns all pipeline components."""

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

        # Channel of the turn currently being processed: "voice" (PC mic/Alt+Z) or
        # "text" (widget / mobile / queue). A turn's answer leaves by the channel it
        # entered: voice is spoken on the PC, text stays silent (rides the bus). Set
        # at the top of _process(); read by the filler callback on the backend thread.
        # Turns are serialized by the FSM, so a plain attribute is race-free.
        self._active_channel = "voice"

        # Set while a voice turn is answering a tool confirmation by voice (spoken
        # question → hotkey → spoken yes/no). Guarded by _state_lock. None otherwise.
        self._voice_confirm: _PendingConfirm | None = None

        # Shared FIFO queue of pending text turns (from the widget / mobile app).
        # Guarded by _state_lock; drained when the FSM returns to IDLE. Voice turns
        # are not queued (they are interactive and foreground). See submit_turn().
        self._queue: deque[str] = deque()

        # Pipeline components (injectable for testing)
        self._tts = tts or PiperSpeaker()
        self._audio = audio or AudioRecorder()
        self._stt = stt or WhisperTranscriber()
        if llm is not None:
            self._llm = llm
        elif config.BACKEND == "native":
            from mirach.harness.build import build_native_backend

            self._llm = build_native_backend(speak_filler=self._on_filler)
        elif config.BACKEND == "opencode_serve":
            from mirach.harness.build import build_opencode_serve_backend

            self._llm = build_opencode_serve_backend(speak_filler=self._on_filler)
        else:
            raise ValueError(
                f"Unknown MIRACH_BACKEND={config.BACKEND!r}. Use 'native' or 'opencode_serve'."
            )
        self._conv = ConversationLog()
        self._system_prompt = ""
        self._obsidian = ObsidianCache(config.OBSIDIAN_VAULT)
        self._user_scripts: list[UserScript] = []

        # Watch the bus so a voice turn can answer tool confirmations by voice.
        self.bus.subscribe(self._on_bus_event)

    # ── State helpers ──────────────────────────────────────────────────

    def _set_state(self, new: State) -> None:
        """Transition to a new state, signaling the idle event when reaching IDLE."""
        with self._state_lock:
            self._state = new
        if new is State.IDLE:
            self._idle.set()
        else:
            self._idle.clear()

    def _check_interrupted(self) -> None:
        """Raise _Interrupted if the user has requested an abort."""
        if self._interrupt.is_set():
            raise _Interrupted()

    # ── Initialization ─────────────────────────────────────────────────

    def load(self) -> None:
        """Load all pipeline components, warm up models, and parse user scripts."""
        self._stt.load()
        self._tts.load()
        self._audio.detect_microphone()
        self._audio.open()
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
        # Warmup Whisper and pre-bake filler phrases so the first real turn is fast.
        self._stt.warmup()
        self._tts.prebake_fillers(i18n.fillers())

    # ── User scripts ───────────────────────────────────────────────────

    @staticmethod
    def _parse_script_metadata(path: Path) -> UserScript | None:
        """Parse # triggers: and # response: metadata from the first lines of a script.

        Returns None if required fields (triggers, response) are missing.
        """
        triggers: list[str] = []
        response = ""
        description = ""

        with open(path) as f:
            for line in f:
                if line.startswith("#!"):
                    continue  # skip shebang
                if not line.startswith("#"):
                    break  # end of metadata block
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
        """Scan the user_scripts/ directory and parse all valid .sh/.py scripts.

        Automatically fixes the executable bit on scripts that have valid
        metadata but lack the execute permission.
        """
        scripts_dir = config.BASE_DIR / "user_scripts"
        if not scripts_dir.is_dir():
            return []

        scripts: list[UserScript] = []
        for entry in sorted(scripts_dir.iterdir()):
            if entry.suffix in (".sh", ".py") and entry.name != ".gitkeep":
                parsed = self._parse_script_metadata(entry)
                if parsed:
                    if not os.access(entry, os.X_OK):
                        mode = entry.stat().st_mode
                        entry.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                        log.info("Fixed executable bit on %s", entry.name)
                    scripts.append(parsed)
        return scripts

    @staticmethod
    def _phrase_in(phrase: str, text: str) -> bool:
        """True if `phrase` appears in `text` on word boundaries (no substring matches).

        Avoids false positives like the trigger "api" matching inside "rápido".
        Both arguments are expected to be lowercase.
        """
        if not phrase:
            return False
        return re.search(rf"\b{re.escape(phrase)}\b", text) is not None

    def _match_user_script(self, text: str) -> UserScript | None:
        """Check if the transcribed text contains any user script trigger phrase."""
        lower = text.lower()
        for script in self._user_scripts:
            for trigger in script.triggers:
                if self._phrase_in(trigger, lower):
                    return script
        return None

    def _match_builtin_trigger(self, text: str) -> tuple[str, str] | None:
        """Check if the transcribed text contains any built-in trigger phrase."""
        lower = text.lower()
        for phrase, (response_key, handler) in BUILTIN_TRIGGERS.items():
            if self._phrase_in(phrase, lower):
                return response_key, handler
        return None

    # ── Main pipeline ──────────────────────────────────────────────────

    def _process(self, text: str | None = None, *, channel: str = "voice") -> None:
        """Run the full pipeline: (stop recording → transcribe →) LLM → speak.

        Runs in a background thread. When `text` is None this is a voice turn and
        steps 1–2 capture+transcribe the recording; when `text` is given it is a
        text turn (widget / mobile / queue drain) that skips straight to the LLM.
        Both paths share steps 3–6, but the answer leaves by `channel`: a voice
        turn is spoken on the PC, a text turn stays silent and rides the bus to the
        widget (see _respond / _on_filler). Always resets state to IDLE in the
        finally block and then drains the next queued turn.
        """
        self._active_channel = channel
        started = time.time()
        try:
            if text is None:
                # Step 1: Stop recording and validate audio length
                audio = self._audio.stop()
                if audio is None or len(audio) < config.SAMPLE_RATE * 0.5:
                    log.info("Empty or too-short audio")
                    self._tts.speak(i18n.t("nothing_recorded"))
                    return

                self._check_interrupted()

                # Step 2: Transcribe
                notify.notify(i18n.t("processing_title"), i18n.t("processing_body"), "microphone")
                text = self._stt.transcribe(audio)
                if not text:
                    self._tts.speak(i18n.t("didnt_hear"))
                    return

                self._check_interrupted()
                notify.notify(i18n.t("you_said"), text)

            # Publish the user's turn to the bus so every connected client renders
            # the user side of the shared conversation (and replays it on resume).
            with contextlib.suppress(Exception):
                from mirach.harness.events import UserTurnEvent

                self.bus.publish(UserTurnEvent(text=text))

            # Step 3: Check built-in triggers (bypass LLM)
            builtin = self._match_builtin_trigger(text)
            if builtin:
                response_key, handler = builtin
                if handler == "conversation":
                    path = show_conversation_html()
                    if path:
                        self._respond(i18n.t(response_key), channel)
                        self._conv.append(i18n.t("assistant"), i18n.t(response_key))
                    else:
                        self._respond(i18n.t("no_conversation"), channel)
                        self._conv.append(i18n.t("assistant"), i18n.t("no_conversation"))
                return

            # Step 4: Check user scripts (bypass LLM)
            matched = self._match_user_script(text)
            if matched:
                log.info("User script triggered: %s", matched.path.name)
                subprocess.Popen([str(matched.path)], start_new_session=True)
                self._respond(matched.response, channel)
                self._conv.append(i18n.t("assistant"), matched.response)
                return

            # Step 5: LLM query (with optional Obsidian context on new sessions)
            # We evaluate session_expired() here (the LLM re-checks it inside
            # query()) because we need the decision *before* the query to start
            # a new conversation log and refresh the Obsidian cache.
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
                self._respond(i18n.t("didnt_understand"), channel)
                return

            # Step 6: Deliver the response on the turn's channel (voice speaks; text
            # already streamed to the bus, so on_bus=True keeps the PC silent).
            self._conv.append(i18n.t("assistant"), result.response)
            notify.notify(i18n.t("assistant"), result.response)
            self._respond(result.response, channel, on_bus=True)
            log.info("Pipeline complete in %.2fs", time.time() - started)
        except _Interrupted:
            log.info("Pipeline interrupted by user")
        except Exception as e:
            log.exception("Pipeline ERROR: %s", e)
            with contextlib.suppress(Exception):
                self._respond(i18n.t("error_occurred"), channel)
        finally:
            self._clear_voice_confirm()
            self._set_state(State.IDLE)
            self._maybe_start_next()

    # ── FSM: toggle ────────────────────────────────────────────────────

    def toggle(self) -> None:
        """Handle a hotkey press. Cycles through IDLE → RECORDING → PROCESSING.

        If currently PROCESSING, interrupts the pipeline and starts a new recording
        (the classic single-key behaviour). The interrupting voice turn takes the
        slot to record — a pending text queue is preserved and drains afterwards.
        """
        with self._state_lock:
            pending = self._voice_confirm
            current = self._state

        # A voice confirmation is waiting: the hotkey answers it instead of
        # interrupting the turn (1st press records the yes/no, 2nd press submits it).
        if pending is not None:
            self._toggle_voice_confirm(pending)
            return

        if current is State.PROCESSING:
            log.info("User interrupt requested (voice)")
            self._interrupt_current()
            # Claim the slot to RECORD before clearing the interrupt latch, so a
            # queued text turn cannot drain into the slot first.
            self._set_state(State.RECORDING)
            self._resume_after_interrupt()
            self._begin_recording()
            return

        if current is State.IDLE:
            self._set_state(State.RECORDING)
            self._begin_recording()
        elif current is State.RECORDING:
            self._set_state(State.PROCESSING)
            threading.Thread(target=self._process, daemon=True).start()

    # ── Text turns + queue (widget / mobile) ───────────────────────────

    @property
    def bus(self):
        """The active backend's ConversationBus (the daemon's server streams it)."""
        return self._llm.bus

    def submit_turn(self, text: str, *, interrupt: bool = False, clear_queue: bool = False) -> dict:
        """Submit a text turn from a remote client (widget / mobile / queue drain).

        interrupt=False → append to the back of the queue (FIFO).
        interrupt=True  → cancel the running turn and insert at the front (priority);
                          clear_queue=True also drops the rest of the queue ("live mode").
        Returns an acknowledgement dict the server relays to the client.
        """
        text = (text or "").strip()
        if not text:
            return {"status": "rejected", "reason": "empty"}

        if interrupt:
            self._interrupt_current()
            with self._state_lock:
                cleared = clear_queue and bool(self._queue)
                if clear_queue:
                    self._queue.clear()
                self._queue.appendleft(text)
            if cleared:
                self._publish_queue_cleared()
            self._resume_after_interrupt()
            self._maybe_start_next()
            return {"status": "accepted", "position": 1}

        with self._state_lock:
            if len(self._queue) >= MAX_QUEUE:
                return {"status": "rejected", "reason": "queue_full"}
            self._queue.append(text)
            position = len(self._queue)
        # Publish before draining so the 'queued' event always precedes the
        # 'user_turn' that settles it in the bus history (clean replay on resume).
        from mirach.harness.events import QueuedTurnEvent

        self._publish_event(QueuedTurnEvent(text=text))
        self._maybe_start_next()
        return {"status": "queued", "position": position}

    def stop(self) -> None:
        """Hard stop: cancel the running turn AND clear the queue, then go idle.

        The stop button on the widget / live mode, and the PC stop hotkey (IPC
        'stop'). Submits no new turn.
        """
        self._interrupt_current()
        with self._state_lock:
            had_queued = bool(self._queue)
            self._queue.clear()
        if had_queued:
            self._publish_queue_cleared()
        self._resume_after_interrupt()
        log.info("Stopped: current run cancelled and queue cleared")

    def confirm(self, tool_call_id: str) -> None:
        """Approve a mid-flight tool confirmation (voice answer or relayed from the server)."""
        self._clear_voice_confirm(tool_call_id)
        self._llm.confirm(tool_call_id)

    def deny(self, tool_call_id: str) -> None:
        """Reject a mid-flight tool confirmation (voice answer or relayed from the server)."""
        self._clear_voice_confirm(tool_call_id)
        self._llm.deny(tool_call_id)

    def reset_session(self) -> None:
        """End the current LLM session (maps to POST /close_session on the HTTP server)."""
        self._llm.reset_session()

    def _on_filler(self, phrase: str) -> None:
        """Filler callback handed to the backend; silent on text turns and confirms.

        Fillers are PC audio, so they only play for a voice turn. Text turns
        (widget / mobile) must not make the PC speak while the user waits, and a
        pending voice confirmation must stay quiet so the spoken question and the
        user's answer aren't talked over.
        """
        if self._active_channel == "voice" and self._voice_confirm is None:
            self._tts.speak_filler(phrase)

    def _respond(self, text: str, channel: str, *, on_bus: bool = False) -> None:
        """Deliver a response on the turn's channel.

        Voice → speak it on the PC. Text → keep the PC silent; if the text isn't
        already on the bus (canned replies — triggers, scripts, errors — not the
        streamed LLM answer), publish a Done bubble so the widget transcript stays
        complete.
        """
        if channel == "voice":
            self._tts.speak(text)
        elif not on_bus:
            from mirach.harness.events import DoneEvent

            self._publish_event(DoneEvent(content=text))

    def _publish_event(self, event) -> None:
        """Publish to the backend's bus, swallowing any backend/bus failure."""
        with contextlib.suppress(Exception):
            self.bus.publish(event)

    def _publish_queue_cleared(self) -> None:
        """Tell clients the pending queue was dropped (stop / clear_queue)."""
        from mirach.harness.events import QueueClearedEvent

        self._publish_event(QueueClearedEvent())

    # ── Voice confirmation (a voice turn answers a tool confirm by voice) ──

    def _on_bus_event(self, event) -> None:
        """Bus subscriber: start a voice-confirm flow when a voice turn needs approval.

        Runs synchronously on the publishing thread (the same publish fans out to
        the SSE server feeding the widget), so it must not block — it only hands
        off to a worker thread. The widget confirm block still appears for every
        channel; the first device to answer wins. Text turns rely on it alone.
        """
        if getattr(event, "type", "") != "awaiting_confirmation":
            return
        if self._active_channel != "voice":
            return
        threading.Thread(target=self._begin_voice_confirm, args=(event,), daemon=True).start()

    def _begin_voice_confirm(self, event) -> None:
        """Speak the confirmation question and arm the auto-deny timeout."""
        tool_call_id = event.tool_call_id
        timer = threading.Timer(
            config.VOICE_CONFIRM_TIMEOUT, self._voice_confirm_timeout, args=(tool_call_id,)
        )
        timer.daemon = True
        with self._state_lock:
            self._voice_confirm = _PendingConfirm(tool_call_id=tool_call_id, timer=timer)
        timer.start()
        question = i18n.t("confirm_question").replace("{action}", self._describe_tool(event))
        self._tts.speak(question)

    def _toggle_voice_confirm(self, pending: _PendingConfirm) -> None:
        """Hotkey press while a voice confirmation is pending.

        First press records the spoken yes/no; second press stops, transcribes,
        and submits the answer off-thread so the IPC handler returns promptly.
        """
        if not pending.recording:
            with self._state_lock:
                if self._voice_confirm is not pending:
                    return  # answered or timed out between toggle's read and here
                pending.recording = True
            pending.timer.cancel()
            self._begin_recording()
            return
        threading.Thread(target=self._finish_voice_confirm, args=(pending,), daemon=True).start()

    def _finish_voice_confirm(self, pending: _PendingConfirm) -> None:
        """Stop the answer recording, transcribe it, and confirm/deny accordingly."""
        audio = self._audio.stop()
        pending.recording = False
        text = self._stt.transcribe(audio) if audio is not None else ""
        log.info("Voice confirmation answer: %r", text)
        if self._is_affirmative(text):
            self.confirm(pending.tool_call_id)
        else:
            self.deny(pending.tool_call_id)

    def _voice_confirm_timeout(self, tool_call_id: str) -> None:
        """Auto-deny a voice confirmation the user never started answering."""
        with self._state_lock:
            pending = self._voice_confirm
            if pending is None or pending.tool_call_id != tool_call_id or pending.recording:
                return  # already answered, superseded, or an answer is in progress
        log.info("Voice confirmation timed out → deny")
        self.deny(tool_call_id)

    def _clear_voice_confirm(self, tool_call_id: str | None = None) -> None:
        """Drop the pending voice confirmation (answered, superseded, or turn ended).

        With a tool_call_id, only clears a matching pending confirm so a stale id
        can't cancel a newer one. Cancels the timeout and stops any in-flight
        answer recording.
        """
        with self._state_lock:
            pending = self._voice_confirm
            if pending is None:
                return
            if tool_call_id is not None and pending.tool_call_id != tool_call_id:
                return
            self._voice_confirm = None
        pending.timer.cancel()
        if pending.recording:
            with contextlib.suppress(Exception):
                self._audio.stop()

    @staticmethod
    def _describe_tool(event) -> str:
        """Build a short spoken description of a tool call for the confirm question."""
        args = getattr(event, "arguments", None) or {}
        for key in ("command", "cmd", "path", "file", "query", "url"):
            val = args.get(key)
            if isinstance(val, str) and val.strip():
                return f"{event.name}: {val.strip()}"
        return event.name

    @staticmethod
    def _is_affirmative(text: str) -> bool:
        """True if a transcribed answer contains a yes-word. Unclear → False (deny)."""
        return any(w in _AFFIRMATIVE_WORDS for w in re.findall(r"\w+", text.lower()))

    # ── Slot arbitration (queue drain vs. voice vs. interrupt) ──────────

    def _begin_recording(self) -> None:
        """Beep, open the mic, and notify — the RECORDING entry actions."""
        notify.play_beep(config.BEEP_START_WAV)
        self._audio.start()
        notify.notify(
            i18n.t("recording_start_title"),
            i18n.t("recording_start_body"),
            "microphone-sensitivity-high",
        )

    def _interrupt_current(self) -> None:
        """Cancel the in-flight turn (if any) and wait for the slot to free.

        Leaves self._interrupt SET on purpose: this suppresses the cancelled
        pipeline's own queue-drain (see _maybe_start_next) so the caller can
        decide what runs next without a race. The caller MUST then call
        _resume_after_interrupt() to clear the latch and re-enable TTS.
        """
        with self._state_lock:
            state = self._state

        if state is State.PROCESSING:
            self._interrupt.set()
            self._llm.interrupt()
            self._tts.interrupt()
            if not self._idle.wait(timeout=3.0):
                log.warning("Pipeline did not release in 3s, forcing IDLE")
                self._set_state(State.IDLE)
        elif state is State.RECORDING:
            self._interrupt.set()
            with contextlib.suppress(Exception):
                self._audio.stop()
            self._set_state(State.IDLE)

    def _resume_after_interrupt(self) -> None:
        """Clear the interrupt latch and re-enable TTS after an interrupt is handled."""
        self._interrupt.clear()
        self._tts.clear_interrupt()

    def _maybe_start_next(self) -> None:
        """If idle and a text turn is queued, pop it and start processing.

        Skips while self._interrupt is set: an interrupt is in progress and its
        caller is arranging the next state/queue, so the slot is spoken for.
        """
        with self._state_lock:
            if self._interrupt.is_set() or self._state is not State.IDLE or not self._queue:
                return
            text = self._queue.popleft()
            self._state = State.PROCESSING
        self._idle.clear()
        # Queued turns come from remote clients (widget / mobile) → text channel.
        threading.Thread(
            target=self._process, kwargs={"text": text, "channel": "text"}, daemon=True
        ).start()

    # ── Entry point ────────────────────────────────────────────────────

    def run(self) -> None:
        """Start the daemon: load components, generate beeps, and serve the socket."""
        log.info("=== Daemon starting ===")
        notify.open_beep_stream()
        notify.generate_beeps()
        _install_shutdown_hooks(self)
        self.load()
        notify.notify(i18n.t("daemon_ready_title"), i18n.t("daemon_ready_body"))
        if config.SERVER_ENABLED:
            from mirach.harness.server import MirachServer

            MirachServer(self, config.SERVER_HOST, config.SERVER_PORT).start()
        SocketServer(on_toggle=self.toggle, on_stop=self.stop).serve_forever()

    def shutdown(self) -> None:
        """Close persistent audio streams. Idempotent; safe to call at shutdown."""
        with contextlib.suppress(Exception):
            self._audio.close()
        with contextlib.suppress(Exception):
            self._tts.close()
        with contextlib.suppress(Exception):
            if hasattr(self._llm, "stop"):
                self._llm.stop()


# ── Shutdown handling ──────────────────────────────────────────────────
_shutdown_played = False
_cleanup_done = False
_shutdown_assistant: Assistant | None = None


def _cleanup_audio() -> None:
    """Close persistent audio streams at shutdown."""
    global _cleanup_done, _shutdown_assistant
    if _cleanup_done:
        return
    _cleanup_done = True
    if _shutdown_assistant is not None:
        _shutdown_assistant.shutdown()
    with contextlib.suppress(Exception):
        notify.close_beep_stream()


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
    """Handle SIGTERM/SIGINT by playing the shutdown beep and exiting."""
    log.warning("Received signal %d, shutting down", signum)
    _play_shutdown_beep()
    _cleanup_audio()
    sys.exit(0)


def _install_shutdown_hooks(assistant: Assistant) -> None:
    """Register signal handlers and atexit callback for graceful shutdown."""
    global _shutdown_assistant
    _shutdown_assistant = assistant
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    atexit.register(_play_shutdown_beep)
    atexit.register(_cleanup_audio)


def main() -> None:
    """Entry point for `python -m mirach` or the installed `mirach` command."""
    Assistant().run()


if __name__ == "__main__":
    main()
