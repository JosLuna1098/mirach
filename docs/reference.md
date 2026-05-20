# Reference

Technical description of Mirach's configuration, architecture, and components.

## Configuration

All settings are environment variables with defaults. Override by exporting before launch or setting in the systemd service file.

### Paths

| Variable | Default | Description |
|---|---|---|
| `MIRACH_BASE_DIR` | `~/mirach` | Project root directory |
| `MIRACH_SOCKET` | `/tmp/mirach.sock` | Unix socket path for daemon-client IPC |
| `MIRACH_SYSTEM_PROMPT` | `~/mirach/system_prompt.md` | Path to the system prompt file |

### Audio

| Variable | Default | Description |
|---|---|---|
| `MIRACH_MIC` | `fifine` | Substring match against microphone name |
| `MIRACH_SAMPLE_RATE` | `48000` | Native sample rate of your microphone |
| `MIRACH_RMS_SILENCE` | `0.005` | RMS threshold below which audio is discarded as silence |

### STT (Whisper)

| Variable | Default | Description |
|---|---|---|
| `MIRACH_WHISPER_MODEL` | `medium` | Model name (any faster-whisper compatible model) |
| `MIRACH_WHISPER_DEVICE` | `cuda` | `cuda` for GPU, `cpu` for CPU-only |
| `MIRACH_WHISPER_COMPUTE` | `int8` | `int8` for lower VRAM, `float16` for max accuracy |
| `MIRACH_WHISPER_LANG` | `es` | ISO 639-1 language code for transcription |
| `MIRACH_WHISPER_BEAM_SIZE` | `3` | Beam size 1-5 (lower = faster, higher = more accurate) |

### TTS (Piper)

| Variable | Default | Description |
|---|---|---|
| `MIRACH_VOICE` | `daniela.onnx` | Filename inside `voices/` directory |
| `MIRACH_VOICE_SPEED` | `1.2` | Piper `length_scale` (>1 = slower, <1 = faster) |

### LLM (OpenCode)

| Variable | Default | Description |
|---|---|---|
| `MIRACH_OPENCODE_MODEL` | `opencode/deepseek-v4-flash-free` | Model identifier for `opencode run` |
| `MIRACH_OPENCODE_TIMEOUT` | `120` | Timeout in seconds for normal queries |
| `MIRACH_OPENCODE_TIMEOUT_CODING` | `300` | Timeout in seconds for coding-related queries (5 min) |
| `MIRACH_SESSION_IDLE_TIMEOUT` | `3600` | Seconds of inactivity before starting a new LLM session (1 hour) |

### User feedback

| Variable | Default | Description |
|---|---|---|
| `MIRACH_LOCALE` | `en` | UI language (`en`, `es`, or custom) |
| `MIRACH_HOTKEY` | `Alt+Z` | Display label shown in notifications (cosmetic only) |
| `MIRACH_FILLER_DELAY` | `6.0` | Seconds between filler phrases during long LLM calls |
| `MIRACH_FILLERS` | _(localized)_ | Pipe-separated override for filler phrases |

### Obsidian (persistent memory)

| Variable | Default | Description |
|---|---|---|
| `MIRACH_OBSIDIAN_VAULT` | `~/ObsidianVault` | Path to Obsidian vault root |
| `MIRACH_OBSIDIAN_CACHE_MAX_AGE` | `300.0` | Max age in seconds before cache is considered stale (5 min) |

## Architecture

### Pipeline overview

```
[Hotkey] → trigger.py ──socket──► daemon (python -m mirach)
                                     │
                                     ├─ AudioRecorder      (sounddevice, callback-based)
                                     ├─ WhisperTranscriber (faster-whisper, CUDA/CPU)
                                     ├─ PiperSpeaker       (piper-tts, streaming)
                                     ├─ OpenCodeBackend    (subprocess: opencode run)
                                     ├─ ConversationLog    (markdown per session)
                                     ├─ ConversationHTML   (styled HTML viewer)
                                     ├─ ObsidianCache      (persistent memory)
                                     ├─ UserScripts        (custom voice commands)
                                     ├─ Notifier           (notify-send + beeps)
                                     └─ SocketServer       (Unix domain socket)
```

### State machine

The assistant operates a three-state FSM:

```
IDLE ──[toggle]──► RECORDING ──[toggle]──► PROCESSING ──[done]──► IDLE
                       ▲                      │
                       │       [toggle]        │
                       └──────────────────────┘
                          (interrupt + re-record)
```

| State | Description |
|---|---|
| `IDLE` | Waiting for hotkey press. No audio capture. |
| `RECORDING` | Microphone is open, audio frames collected in a buffer. |
| `PROCESSING` | Pipeline running in background thread: stop recording → transcribe → LLM → speak. |

### Source layout

```
mirach/
  ├── __main__.py          # Entry point: `python -m mirach`
  ├── __init__.py          # Package metadata, version
  ├── assistant.py         # Orchestrator + FSM + shutdown hooks + user scripts
  ├── audio.py             # Thread-safe microphone capture (sounddevice)
  ├── stt.py               # WhisperTranscriber with warmup + downsampling
  ├── tts.py               # PiperSpeaker with streaming + pre-baked fillers
  ├── llm.py               # OpenCodeBackend with progressive feedback
  ├── ipc.py               # Unix socket server (toggle/ping protocol)
  ├── notify.py            # Desktop notifications + beep WAV generation
  ├── conversation.py      # Markdown conversation files + latest.md symlink
  ├── conversation_html.py # HTML conversation viewer (dark theme, chat layout)
  ├── obsidian_cache.py    # In-memory cache for Obsidian vault files
  ├── config.py            # All MIRACH_* env vars with defaults
  ├── i18n.py              # Localization strings + filler phrases
  └── logging_setup.py     # Rotating file logger + stdout for journalctl

trigger.py                 # Standalone hotkey client (sends "toggle" to socket)
run_daemon.sh              # Launcher with CUDA 12 library path setup
pyproject.toml             # Package metadata, dependencies, tool config
install.py                 # Interactive setup wizard
install.sh                 # Non-interactive shell installer
system_prompt.example.md   # Template for personalized system prompt
mirach.service.example     # Template for systemd user service

user_scripts/              # User-defined voice-triggered scripts (gitignored content)
skills/                    # OpenCode skills (installed to ~/.config/opencode/skills/)
```

### Dependencies

| Package | Purpose | Required |
|---|---|---|
| `faster-whisper>=1.2` | Speech-to-text (Whisper via CTranslate2) | Yes |
| `piper-tts>=1.4` | Text-to-speech (local neural TTS) | Yes |
| `sounddevice>=0.5` | Audio I/O (microphone capture + playback) | Yes |
| `numpy>=1.26` | Numerical operations (audio processing) | Yes |
| `scipy>=1.11` | High-quality polyphase resampling | Optional (quality extra) |
| `pytest>=8.0` | Test framework | Dev only |
| `ruff>=0.6` | Linting and formatting | Dev only |

### IPC protocol

The Unix socket accepts two messages:

| Message | Response | Description |
|---|---|---|
| `toggle` | _(none)_ | Triggers the FSM state transition |
| `ping` | `pong` | Health check for the daemon |

### Session persistence

The OpenCode session ID is persisted to `~/.cache/mirach/session_id`. On daemon startup:

1. If the file exists, the session ID and its last modification time are loaded
2. If the time since last interaction exceeds `SESSION_IDLE_TIMEOUT`, a new session is created
3. On a new session, the system prompt and Obsidian context are injected into the first query

### User script format

Scripts in `user_scripts/` are parsed for metadata comments:

```bash
#!/bin/bash
# triggers: phrase one, phrase two
# response: Spoken confirmation.
# description: Optional description.

# Script body runs here
```

- `triggers:` — comma-separated, case-insensitive substring matching
- `response:` — text spoken after script execution
- `description:` — for human reference only, not used by the daemon

### Beep frequencies

| Beep | Frequency | Duration | Purpose |
|---|---|---|---|
| Start | 1320 Hz | 60 ms | Signals recording has started |
| Process | 660 Hz | 80 ms | Signals transcription has begun |
| Shutdown | 660 Hz → 330 Hz | 120 ms each, 40 ms gap | Signals daemon is stopping |

### Progressive LLM feedback timeline

| Time | Action |
|---|---|
| 0s | Process beep, OpenCode subprocess launched |
| 0-10s | Normal filler phrases every `FILLER_DELAY` seconds |
| 10s | Desktop notification + filler |
| 30s | "Still working" spoken message |
| 60s | "Complex query" message + desktop notification |
