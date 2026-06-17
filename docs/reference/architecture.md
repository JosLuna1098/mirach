# Architecture Reference

## System overview

Mirach runs as a background daemon on your Linux desktop and exposes an HTTP/SSE API used by the web widget and the Android app. A single hotkey triggers the voice pipeline; the same pipeline can be driven remotely from the mobile app.

```
[Hotkey] ──► trigger.py ──socket──► Assistant (FSM)
                                         │
                          ┌──────────────┼──────────────┐
                          ▼              ▼               ▼
                   AudioRecorder   WhisperTranscriber  PiperSpeaker
                    (sounddevice)   (faster-whisper)   (piper-tts)
                                         │
                                    LLMBackend (protocol)
                                    ┌────┴────┐
                              opencode_serve  native
                              (opencode CLI) (Ollama/vLLM…)
                                         │
                                    ConversationBus ──► HTTP/SSE server
                                                             │
                                                    ┌────────┴────────┐
                                                  Widget        Android app
                                                (browser)    (flutter/mobile)
```

## State machine — `assistant.py`

`Assistant` owns a three-state FSM. `toggle()` is the only public entry point, called by the Unix socket server on every `"toggle"` message.

```
IDLE ──[toggle]──► RECORDING ──[toggle]──► PROCESSING ──[done]──► IDLE
                                                │
                                           [toggle]  interrupts pipeline
                                                │
                                             IDLE (re-enter)
```

| State | Description |
|---|---|
| `IDLE` | Waiting for hotkey press. No audio capture. |
| `RECORDING` | Microphone is open; audio frames collected in a buffer. |
| `PROCESSING` | Background thread running: `AudioRecorder.stop()` → `WhisperTranscriber.transcribe()` → `LLMBackend.query()` → `PiperSpeaker.speak()`. |

A second `toggle()` during PROCESSING interrupts: `LLM.interrupt()` + `TTS.interrupt()` are called concurrently; the pipeline thread sets the FSM back to IDLE.

## LLM backends — `mirach/harness/`

Two backends implement the `LLMBackend` protocol (`llm_types.py`). Select via `MIRACH_BACKEND`.

**`opencode_serve` (default)** — `mirach/harness/providers/opencode.py`

Spawns and supervises `opencode serve`. Creates or reuses a session, translates the SSE event stream (`message.part.delta`, `permission.updated`, `session.idle`) into `ConversationBus` events, and enforces `PolicyEngine` on every `permission.updated`. Session resets after `MIRACH_SESSION_IDLE_TIMEOUT` idle seconds.

**`native`** — `mirach/harness/native_backend.py`

Runs a full inner tool-use REPL against any OpenAI-compatible endpoint (Ollama, llama.cpp, vLLM…). Tool invocation protocol: `auto | native | prompted`. Policy enforced before every tool execution. History in-memory; session resets after the same idle timeout.

## Policy engine — `mirach/harness/policy/`

`PolicyEngine` evaluates every tool call before execution against `policy.yaml`. Rules are `allow` or `deny` with glob patterns on tool name and arguments. Matched `deny` rules block execution and surface a `permission.updated` event with `status: denied`. Unmatched calls that require confirmation trigger `status: awaiting_confirmation`.

## ConversationBus — `mirach/harness/events.py`

An in-process publish/subscribe channel. The active backend publishes typed events (`queued`, `user_turn`, `text_delta`, `tool_call`, `tool_result`, `awaiting_confirmation`, `done`, `error`, `cost`). The HTTP server fans them out to SSE subscribers; the UI thread drives TTS from the same bus.

## HTTP/SSE server — `mirach/harness/server.py`

A Python stdlib `ThreadingHTTPServer` that exposes the REST + SSE API. Enabled by default; disable with `MIRACH_SERVER_ENABLED=0`.

See [HTTP/SSE API Reference](http-api.md) for the full endpoint contract.

## STT — `stt.py`

`WhisperTranscriber` captures at `MIRACH_SAMPLE_RATE` (default 48 kHz), downsamples to Whisper's required 16 kHz via polyphase resampling (scipy) or a boxcar fallback, and runs inference on GPU or CPU. A warmup pass on a silent buffer runs at startup to avoid cold-start latency.

## TTS — `tts.py`

`PiperSpeaker` synthesizes chunks that stream directly into a `sounddevice.OutputStream` — playback begins before synthesis finishes. A `_stream_lock` serializes concurrent `speak()` calls (main response + filler loop). Short filler phrases are pre-baked to WAV files at startup (`prebake_fillers`) and played via `sd.play()`.

## i18n — `i18n.py`

Desktop locale chosen at import time via `MIRACH_LOCALE`. Add a new locale by extending the `STRINGS` and `FILLERS` dicts. Strings not present in the current locale fall back to English.

The Android app uses a separate ARB-based system (`mobile/lib/l10n/`) managed by `flutter gen-l10n`. The app locale is persisted under the `mirach_lang` key in `flutter_secure_storage`.

## ConversationLog — `conversation.py`

Each session writes one Markdown file under `logs/conversations/` and updates a `latest.md` symlink. A new session starts when the idle timeout elapses.

## Source layout

```
mirach/
  __main__.py          — entry point: `python -m mirach`
  assistant.py         — orchestrator, FSM, shutdown hooks
  audio.py             — thread-safe microphone capture (sounddevice)
  stt.py               — WhisperTranscriber with warmup + downsampling
  tts.py               — PiperSpeaker with streaming + pre-baked fillers
  llm_types.py         — LLMBackend protocol + _strip_markdown()
  ipc.py               — Unix socket server (toggle / ping)
  conversation.py      — Markdown logs + latest.md symlink
  conversation_html.py — styled HTML viewer (dark theme, chat layout)
  obsidian_cache.py    — in-memory Obsidian vault reader (session context)
  config.py            — all MIRACH_* env vars with defaults
  i18n.py              — desktop locale strings + filler phrases
  langpack.py          — locale helper used by i18n
  notify.py            — desktop notifications + beep WAV generation
  logging_setup.py     — rotating file logger + stdout for journalctl
  cli.py               — `mirach` CLI entry point
  harness/
    events.py          — ConversationBus + typed event schema
    server.py          — HTTP/SSE server (REST API + widget)
    _widget.py         — embedded web widget HTML
    loop.py            — native backend tool-use REPL (AgentLoop)
    native_backend.py  — NativeBackend: OpenAI-compatible endpoint
    context.py         — ContextManager (compaction strategy)
    build.py           — conversation history builder
    tool_protocol.py   — tool call format detection / normalization
    providers/
      base.py          — LLMBackend abstract base
      opencode.py      — OpenCodeServeBackend (opencode CLI)
      openai_compat.py — raw OpenAI-compatible provider
    policy/
      engine.py        — PolicyEngine: allow/deny/confirm rules
      schema.py        — policy.yaml schema
    tools/
      registry.py      — tool registration
      shell.py         — bash tool
      files.py         — file read/write tools
      web.py           — web search tool
      memory.py        — Obsidian memory tool

trigger.py             — hotkey client (sends "toggle" to socket)
run_daemon.sh          — CUDA 12 library path setup + daemon launcher
pyproject.toml         — package metadata and dependencies
install.py             — interactive setup wizard
bootstrap.sh           — one-liner installer (system deps → clone → wizard)
policy.yaml            — tool permission rules (gitignored; personal)
system_prompt.md       — LLM system prompt (gitignored; personal)
mirach.env             — local config overrides (gitignored; personal)

mobile/                — Android companion app (Flutter)
voices/                — Piper voice models (gitignored; downloaded by installer)
logs/                  — daemon logs + conversation Markdown files
```

## Beep frequencies

| Beep | Frequency | Duration | Purpose |
|---|---|---|---|
| Start recording | 1320 Hz | 60 ms | Signals mic is open |
| Begin processing | 660 Hz | 80 ms | Signals transcription started |
| Shutdown | 660 Hz → 330 Hz | 120 ms + 40 ms gap + 120 ms | Daemon stopping |
