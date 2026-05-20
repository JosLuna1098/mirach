# Mirach Documentation

Local-first voice assistant daemon. Press a hotkey, talk, get an answer spoken back — with conversation memory, tool use, and ~3 s round-trip latency.

## Quick start

```bash
git clone https://github.com/JosLuna1098/mirach ~/mirach && python3 ~/mirach/install.py
```

## What is Mirach?

Mirach is a voice assistant that runs as a background daemon on your Linux desktop:

- **STT**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — Whisper `medium` on GPU, ~0.5 s
- **LLM**: [OpenCode CLI](https://opencode.ai) — your choice of model with full tool ecosystem
- **TTS**: [Piper](https://github.com/rhasspy/piper) — local neural TTS, ~0.3 s
- **Control**: Single hotkey (default `Alt+Z`) for record, process, and interrupt

## How it works

1. Press your hotkey → high beep → start talking
2. Press again → low beep → Mirach transcribes, queries the LLM, speaks the answer
3. Press during processing → interrupts immediately, starts new recording

## Key features

- **No always-on listening** — mic only opens on hotkey
- **Session persistence** — conversations survive daemon restarts
- **Progressive feedback** — fillers and notifications during long LLM calls
- **User scripts** — custom voice-triggered commands without LLM overhead
- **Bilingual** — English and Spanish UI, triggers, and filler phrases
- **Extensible** — OpenCode skills for web search, app control, system monitoring, and more

## Documentation structure

This documentation follows the [Diátaxis framework](https://diataxis.fr/):

| Section | Purpose |
|---|---|
| **[Tutorial](tutorial/get-started.md)** | Learn by doing — install and have your first conversation |
| **[How-to Guides](how-to/user-scripts.md)** | Solve specific problems — add scripts, change voices, troubleshoot |
| **[Reference](reference/configuration.md)** | Technical details — all configuration options, architecture |
| **[Explanation](explanation/design-decisions.md)** | Understand the why — design decisions and tradeoffs |

## Requirements

- **Linux desktop** (Wayland or X11 with `notify-send`)
- **Python 3.11+**
- **NVIDIA GPU with CUDA 12** (CPU mode works with higher latency)
- **A microphone**

## Next steps

- Follow the [Get Started tutorial](tutorial/get-started.md) to install and configure Mirach
- Read the [architecture explanation](explanation/design-decisions.md) to understand the design
- Browse the [configuration reference](reference/configuration.md) to tune every knob
