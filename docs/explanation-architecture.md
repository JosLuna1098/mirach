# Explanation: Why Mirach is Built This Way

This document explains the design decisions behind Mirach. It's for understanding, not for following steps.

## The problem Mirach solves

Most voice assistants fall into one of two categories:

1. **Cloud-based** (Siri, Alexa, Google Assistant): Always listening, your data lives on someone else's servers, and you can't customize the behavior beyond what the vendor allows.

2. **Local but limited** (Mycroft, Rhasspy): Privacy-respecting, but the AI capabilities are weak — rule-based intents, limited natural language understanding, and no tool use.

Mirach sits in the middle: **local-first STT and TTS** for privacy and speed, with a **cloud LLM** (or local via Ollama) for intelligence. The mic only opens on hotkey — no always-on listening.

## Why a daemon, not a CLI

You could build a voice assistant as a simple script: record → transcribe → query → speak → exit. But that has a fundamental latency problem:

- Whisper takes 2-5 seconds to load the model on first run
- Piper takes 1-2 seconds to load the voice model
- The cold start happens **every time** you invoke the script

A daemon solves this by keeping both models in RAM permanently. The first invocation pays the load cost; every subsequent invocation is near-instant.

## Why a single hotkey for everything

Most tools use separate buttons for "start recording" and "stop recording." Mirach uses one key for three actions:

| State | Hotkey does |
|---|---|
| IDLE | Start recording |
| RECORDING | Stop recording, start processing |
| PROCESSING | Interrupt, start new recording |

This design comes from how people actually use voice assistants: you want to **interrupt** when the response is wrong, and immediately say something different. A separate "stop" button would add an extra step.

The beep feedback tells you which state you're in:
- **High beep** (1320 Hz) = recording started
- **Low beep** (660 Hz) = processing started
- **Descending tones** (660→330 Hz) = daemon shutting down

## Why OpenCode as the LLM backend

Mirach doesn't talk to an LLM API directly. Instead, it runs `opencode run` as a subprocess. This might seem indirect, but it has several advantages:

1. **Model flexibility**: Change models without changing Mirach code — just set `MIRACH_OPENCODE_MODEL`
2. **Tool ecosystem**: OpenCode provides bash execution, file I/O, and custom commands as first-class capabilities
3. **Session management**: OpenCode handles conversation history internally
4. **Authentication**: OpenCode manages API keys and provider configuration

The tradeoff is subprocess overhead (~100ms), but this is negligible compared to LLM response times (seconds).

## Why Whisper medium + int8 instead of large-v3-turbo + float16

The original Mirach used `large-v3-turbo` with `float16` compute. This gave ~0.3s transcription but consumed ~2.3 GB of VRAM. The switch to `medium` with `int8` compute changed the balance:

| Config | VRAM | Speed | Accuracy |
|---|---|---|---|
| large-v3-turbo + float16 | ~2.3 GB | ~0.3s | Highest |
| medium + int8 | ~700 MB | ~0.5s | Good |

The 0.2s difference is imperceptible to users (the LLM call takes seconds). The 1.6 GB VRAM savings means Mirach can coexist with other GPU workloads (IDEs, browsers with GPU acceleration, local models).

## Why user scripts instead of hardcoded voice patterns

The original Mirach had hardcoded trigger phrases in `assistant.py` for things like "focus mode" and "toggle nightlight." This had three problems:

1. **Not portable**: Your triggers are personal — they shouldn't be in a shared repo
2. **Not extensible**: Adding a new trigger required editing Python code and restarting
3. **Not discoverable**: There was no documentation of what triggers existed

The `user_scripts/` system solves all three:
- Scripts live in a gitignored directory (personal, not committed)
- Adding a trigger is as simple as creating a file with `# triggers:` comments
- The scripts are self-documenting (the `# description:` field)

## Why progressive feedback during long LLM calls

When an LLM takes 30+ seconds, silence is indistinguishable from failure. Users will press the hotkey again, thinking nothing happened, or assume the daemon crashed.

Mirach provides escalating feedback:

| Time | Feedback | Why |
|---|---|---|
| 0-10s | Normal fillers ("Hmm", "One moment") | Signals the assistant is alive |
| 10s | Desktop notification | Visual confirmation for users who muted audio |
| 30s | "Still working on it" | Acknowledges the delay explicitly |
| 60s | "Complex query" + notification | Sets expectations for very long queries |

The fillers are pre-baked as WAV files at startup so they play with near-zero latency — no synthesis delay during the filler itself.

## Why the conversation HTML viewer

The original `view_conversation.sh` depended on `bat` or `glow` — terminal markdown renderers that many users don't have installed. When neither was available, the script fell back to `cat`, which showed raw Markdown.

The Python-based `conversation_html.py` generates a self-contained HTML file with:
- Dark theme matching the assistant's aesthetic
- Chat-style layout (user on right, assistant on left)
- No external dependencies (CSS is inline)
- Opens in the default browser via `xdg-open`

The file goes to `/tmp/` so the OS cleans it up automatically — no clutter.

## Why session persistence

Without session persistence, every daemon restart starts a fresh LLM conversation. This means:
- You lose context mid-thought if the daemon crashes
- Systemd restarts (common during updates) erase conversation history
- The LLM forgets what you were working on

By persisting the OpenCode session ID to `~/.cache/mirach/session_id`, conversations survive:
- Daemon restarts
- System reboots
- Service updates

The 1-hour idle timeout ensures stale sessions eventually expire, so the LLM doesn't carry irrelevant context from days ago.

## Why Markdown for conversation logs

Conversations are saved as Markdown, not JSON or a database, because:

1. **Human-readable**: You can `cat` a conversation file and understand it immediately
2. **Git-friendly**: If you ever want to version your conversations, diff works naturally
3. **Tool-compatible**: Any Markdown viewer, converter, or processor can read them
4. **Simple**: No schema migrations, no database setup, no ORM

The `latest.md` symlink provides quick access without needing to know the timestamp.
