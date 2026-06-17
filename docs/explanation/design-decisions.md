# Design Decisions

## Local STT and TTS, cloud LLM

Mirach keeps speech-to-text and text-to-speech local (Whisper and Piper) but delegates the LLM to a cloud or local backend via OpenCode or a native OpenAI-compatible endpoint. This balances:

- **Privacy**: Voice recordings never leave your machine. Only the transcribed text is sent to the LLM.
- **Speed**: Local STT and TTS each add ~0.5 s of latency, independent of network conditions.
- **Flexibility**: You can point the native backend at a local Ollama instance for fully offline operation.

## Daemon with models in RAM

Models stay loaded permanently. Loading Whisper and Piper on every invocation would add 3–7 seconds of cold-start latency per interaction — unacceptable for a conversational assistant.

## Single hotkey, three states

One key for record, process, and interrupt. This matches how people actually use voice assistants: you want to interrupt a wrong response and immediately say something different, without reaching for a second key.

## Agentic harness

Rather than calling the LLM once and playing back the answer, Mirach runs an inner loop that handles tool calls, confirmations, and context compaction. The `opencode_serve` backend delegates this entirely to the `opencode` CLI (which has its own tool ecosystem and session management). The `native` backend runs the loop natively against any OpenAI-compatible endpoint.

This split means you get the full OpenCode skill ecosystem by default while keeping the option to run locally with Ollama for privacy-sensitive workflows.

## Policy engine before every tool call

The policy engine evaluates `policy.yaml` before any tool executes. This provides a configurable safety layer: `deny` rules block execution outright; other rules gate on explicit user confirmation. The mobile app and web widget surface confirmations as actionable notifications — you can approve or deny from your phone while the PC is unattended.

## HTTP/SSE visibility layer

A minimal stdlib HTTP server publishes conversation events as Server-Sent Events. This decouples the pipeline from any client: the browser widget, the Android app, and future clients all subscribe to the same event stream. The server adds no external dependencies (no FastAPI, no asyncio framework).

## Android companion app

The phone is a second screen for a desktop assistant. The design constraints:
- **No always-on listening**: the phone doesn't do VAD or wake-word detection; you initiate.
- **No audio routing to phone**: the PC speaks on its own speakers; the phone just shows the transcript and lets you read responses with the phone's TTS if you prefer.
- **Background presence via foreground service**: when you leave the app, a foreground service opens its own SSE connection and shows the current state in a persistent notification, including action buttons for approval/denial.

## Whisper medium + int8

The original setup used `large-v3-turbo` with `float16` (~2.3 GB VRAM). The switch to `medium` with `int8` (~700 MB VRAM) trades 0.2 s of transcription speed for 1.6 GB of VRAM savings — a good trade since the LLM call takes seconds anyway.

## Progressive feedback

During long LLM calls, escalating feedback (spoken fillers → desktop notifications → "still working" messages) prevents users from thinking the daemon has crashed. Fillers are pre-baked as WAV files for zero-latency playback.

## Bilingual desktop + mobile

Desktop strings and filler phrases live in `i18n.py` under locale keys (`en`, `es`). Mobile strings use the `flutter gen-l10n` ARB pipeline, which generates pure-Dart lookup classes that work without a `BuildContext` — the background isolate can therefore call `lookupAppLocalizations(Locale(code))` to localize notification text without any platform channel.

## User scripts over hardcoded patterns

Custom voice commands live in a gitignored `user_scripts/` directory with metadata comments. This makes triggers personal (not in the repo), extensible (just add a file), and self-documenting. LLM overhead is bypassed entirely for matched phrases.

## Markdown conversation logs

Conversations are saved as Markdown, not JSON or a database. Human-readable, git-friendly, and compatible with any Markdown tool. The `latest.md` symlink provides quick access without browsing timestamped files.

## Session persistence

The OpenCode session ID is saved to disk so conversations survive daemon restarts and reboots. A configurable idle timeout ensures stale sessions eventually expire and a fresh context is injected.

## mirach.env for local configuration

All tunables are environment variables. `run_daemon.sh` loads `mirach.env` (gitignored) before starting the daemon, giving a single place to configure voice, locale, server host, and API keys without touching the systemd unit. The systemd unit loads the same variables via `Environment=` lines; a separate `EnvironmentFile` in a drop-in handles secrets (API keys).
