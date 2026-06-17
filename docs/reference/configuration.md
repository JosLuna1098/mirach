# Configuration Reference

All settings are `MIRACH_*` environment variables with sensible defaults. Set them in `mirach.env` (loaded by `run_daemon.sh`) or as `Environment=` lines in the systemd service.

Precedence (highest → lowest): shell environment → `mirach.env` → built-in defaults.

## Paths

| Variable | Default | Description |
|---|---|---|
| `MIRACH_BASE_DIR` | script directory | Project root. Resolved automatically by `run_daemon.sh`; override only if logs/voices live elsewhere. |
| `MIRACH_SOCKET` | `/tmp/mirach.sock` | Unix socket path for hotkey IPC. |
| `MIRACH_SYSTEM_PROMPT` | `<BASE_DIR>/system_prompt.md` | LLM system prompt file. |

## Audio capture

| Variable | Default | Description |
|---|---|---|
| `MIRACH_MIC` | _(empty)_ | Substring match against your microphone's device name. Empty = system default input. |
| `MIRACH_SAMPLE_RATE` | `48000` | Native mic sample rate (Hz). Most USB mics: 48000. |
| `MIRACH_RMS_SILENCE` | `0.005` | RMS threshold below which audio is discarded as silence. |

## STT (Whisper)

| Variable | Default | Description |
|---|---|---|
| `MIRACH_WHISPER_MODEL` | `medium` | Model name. `medium` = multilingual; `medium.en` = English-only. |
| `MIRACH_WHISPER_DEVICE` | `cuda` | `cuda` for GPU, `cpu` for CPU-only. |
| `MIRACH_WHISPER_COMPUTE` | `int8` | `float16` (GPU, higher accuracy) or `int8` (lower VRAM). |
| `MIRACH_WHISPER_LANG` | `es` | ISO 639-1 language code for transcription (e.g. `en`, `es`). |
| `MIRACH_WHISPER_BEAM_SIZE` | `3` | Beam size 1–5. Lower = faster, higher = marginally more accurate. |

## TTS (Piper)

| Variable | Default | Description |
|---|---|---|
| `MIRACH_VOICE` | `en_US-lessac-low.onnx` | Voice model filename inside `voices/`. |
| `MIRACH_VOICE_SPEED` | `1.2` | Piper `length_scale`. `>1` = slower, `<1` = faster. |
| `MIRACH_VOICE_CONFIRM_TIMEOUT` | `20.0` | Seconds to wait for a voice confirmation answer before timing out. |

## Backend

| Variable | Default | Description |
|---|---|---|
| `MIRACH_BACKEND` | `opencode_serve` | LLM backend: `opencode_serve` or `native`. |
| `MIRACH_SESSION_IDLE_TIMEOUT` | `3600` | Seconds of inactivity before the LLM session is reset. |

### opencode_serve backend

| Variable | Default | Description |
|---|---|---|
| `MIRACH_OPENCODE_BIN` | `opencode` | Path or name of the `opencode` binary. |
| `MIRACH_OPENCODE_SERVE_HOST` | `127.0.0.1` | Address where `opencode serve` listens. |
| `MIRACH_OPENCODE_SERVE_PORT` | `0` | Port for `opencode serve` (0 = random free port). |
| `MIRACH_OPENCODE_SERVE_PROVIDER_ID` | _(empty)_ | Provider to pass to `opencode serve`. Empty = opencode's configured default. |
| `MIRACH_OPENCODE_SERVE_MODEL_ID` | _(empty)_ | Model to pass to `opencode serve`. Empty = opencode's configured default. |
| `MIRACH_OPENCODE_SERVE_STARTUP_TIMEOUT` | `15.0` | Seconds to wait for `opencode serve` to print its URL before failing. |
| `MIRACH_OPENCODE_SERVE_LOG` | _(empty)_ | Set to any value to pass `--print-logs` to `opencode serve`. |

### native backend

| Variable | Default | Description |
|---|---|---|
| `MIRACH_NATIVE_BASE_URL` | `http://localhost:11434` | OpenAI-compatible endpoint base URL (Ollama, llama.cpp, vLLM…). |
| `MIRACH_NATIVE_MODEL` | `qwen3:14b` | Model name as the provider knows it. |
| `MIRACH_NATIVE_API_KEY` | `ollama` | API key (use `ollama` for Ollama, otherwise your provider key). |
| `MIRACH_NATIVE_NUM_CTX` | `32768` | Context window size in tokens. |
| `MIRACH_NATIVE_TIMEOUT` | `120.0` | Request timeout in seconds. |
| `MIRACH_NATIVE_TEMPERATURE` | `0.0` | Sampling temperature. |
| `MIRACH_NATIVE_TOOL_PROTOCOL` | `auto` | Tool call format: `auto`, `native`, or `prompted`. |
| `MIRACH_NATIVE_POLICY` | `<BASE_DIR>/policy.yaml` | Path to the tool permission rules file. |

## Context compaction

| Variable | Default | Description |
|---|---|---|
| `MIRACH_CONTEXT_STRATEGY` | `none` | History compaction strategy: `none`, `sliding`, or `summarize`. |
| `MIRACH_CONTEXT_MAX_TOKENS` | `32768` | Token budget before compaction kicks in. |

## Locale and user feedback

| Variable | Default | Description |
|---|---|---|
| `MIRACH_LOCALE` | `en` | Desktop UI language (`en`, `es`, or a custom locale added to `i18n.py`). |
| `MIRACH_HOTKEY` | `Alt+Z` | Display label in notifications (cosmetic; actual binding is in your compositor). |
| `MIRACH_FILLER_DELAY` | `6.0` | Seconds between spoken filler phrases during long LLM calls. |
| `MIRACH_FILLERS` | _(localized)_ | Pipe-separated override for fillers, e.g. `"Wait.\|Thinking."`. |

## HTTP/SSE server (widget + mobile API)

| Variable | Default | Description |
|---|---|---|
| `MIRACH_SERVER_ENABLED` | `1` | Set to `0` to disable the HTTP server entirely. |
| `MIRACH_SERVER_HOST` | `127.0.0.1` | Bind address. Set to `0.0.0.0` to allow connections from the Android app. |
| `MIRACH_SERVER_PORT` | `7270` | TCP port the server listens on. |

## Web search

| Variable | Default | Description |
|---|---|---|
| `MIRACH_SEARCH_REGION` | `wt-wt` | DuckDuckGo region code (e.g. `us-en`, `es-es`, `mx-es`). |

## Obsidian (persistent memory)

| Variable | Default | Description |
|---|---|---|
| `MIRACH_OBSIDIAN_VAULT` | `~/ObsidianVault` | Path to your Obsidian vault root. |
