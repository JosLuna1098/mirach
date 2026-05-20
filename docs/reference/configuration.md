# Configuration Reference

All settings are environment variables with sensible defaults. Override by exporting before launch or setting in the systemd service file.

## Paths

| Variable | Default | Description |
|---|---|---|
| `MIRACH_BASE_DIR` | `~/mirach` | Project root directory |
| `MIRACH_SOCKET` | `/tmp/mirach.sock` | Unix socket path for daemon-client IPC |
| `MIRACH_SYSTEM_PROMPT` | `~/mirach/system_prompt.md` | Path to the system prompt file |

## Audio capture

| Variable | Default | Description |
|---|---|---|
| `MIRACH_MIC` | `fifine` | Substring match against microphone name |
| `MIRACH_SAMPLE_RATE` | `48000` | Native sample rate of your microphone |
| `MIRACH_RMS_SILENCE` | `0.005` | RMS threshold below which audio is discarded as silence |
| `MIRACH_MAX_RECORDING_SEC` | `60.0` | Maximum recording duration in seconds (safety cap to prevent memory issues) |

## STT (Whisper)

| Variable | Default | Description |
|---|---|---|
| `MIRACH_WHISPER_MODEL` | `medium` | Model name (any faster-whisper compatible model) |
| `MIRACH_WHISPER_DEVICE` | `cuda` | `cuda` for GPU, `cpu` for CPU-only |
| `MIRACH_WHISPER_COMPUTE` | `int8` | `int8` for lower VRAM, `float16` for max accuracy |
| `MIRACH_WHISPER_LANG` | `es` | ISO 639-1 language code for transcription |
| `MIRACH_WHISPER_BEAM_SIZE` | `3` | Beam size 1-5 (lower = faster, higher = more accurate) |

## TTS (Piper)

| Variable | Default | Description |
|---|---|---|
| `MIRACH_VOICE` | `daniela.onnx` | Filename inside `voices/` directory |
| `MIRACH_VOICE_SPEED` | `1.2` | Piper `length_scale` (>1 = slower, <1 = faster) |

## LLM (OpenCode)

| Variable | Default | Description |
|---|---|---|
| `MIRACH_OPENCODE_MODEL` | `opencode/deepseek-v4-flash-free` | Model identifier for `opencode run` |
| `MIRACH_OPENCODE_TIMEOUT` | `120` | Timeout in seconds for normal queries |
| `MIRACH_OPENCODE_TIMEOUT_CODING` | `300` | Timeout in seconds for coding-related queries (5 min) |
| `MIRACH_SESSION_IDLE_TIMEOUT` | `3600` | Seconds of inactivity before starting a new LLM session (1 hour) |

## User feedback

| Variable | Default | Description |
|---|---|---|
| `MIRACH_LOCALE` | `en` | UI language (`en`, `es`, or custom) |
| `MIRACH_HOTKEY` | `Alt+Z` | Display label shown in notifications (cosmetic only) |
| `MIRACH_FILLER_DELAY` | `6.0` | Seconds between filler phrases during long LLM calls |
| `MIRACH_FILLERS` | _(localized)_ | Pipe-separated override for filler phrases, e.g. `"Wait.|Thinking."` |

## Obsidian (persistent memory)

| Variable | Default | Description |
|---|---|---|
| `MIRACH_OBSIDIAN_VAULT` | `~/ObsidianVault` | Path to Obsidian vault root |
| `MIRACH_OBSIDIAN_CACHE_MAX_AGE` | `300.0` | Max age in seconds before cache is considered stale (5 min) |
