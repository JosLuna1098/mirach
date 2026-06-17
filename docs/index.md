# Mirach Documentation

Local-first voice assistant daemon for Linux. Press a hotkey, talk, get an answer spoken back — with conversation memory, agentic tool use, a web widget, and an Android companion app.

## Quick start

```bash
git clone https://github.com/JosLuna1098/mirach ~/mirach && python3 ~/mirach/install.py
```

## What is Mirach?

Mirach runs as a background daemon on your Linux desktop:

- **STT**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — Whisper `medium` on GPU, ~0.5 s
- **LLM**: an agentic backend — [OpenCode CLI](https://opencode.ai) by default, or any local OpenAI-compatible endpoint (Ollama, llama.cpp, vLLM)
- **TTS**: [Piper](https://github.com/rhasspy/piper) — local neural TTS, ~0.3 s
- **Control**: a single hotkey (default `Alt+Z`) for record, process, and interrupt
- **Remote**: an HTTP/SSE server powering a browser widget and an Android app

## How it works

1. Press your hotkey → high beep → start talking
2. Press again → low beep → Mirach transcribes, runs the LLM (with tools), and speaks the answer
3. Press during processing → interrupts immediately, starts a new recording

The LLM runs inside an agentic loop: it can call tools (shell, file access, web search, memory), and a policy engine decides which calls run automatically and which need your confirmation. Confirmations surface on the desktop, the web widget, and the Android app.

## Capabilities

- **No always-on listening** — the mic only opens on hotkey
- **Agentic tool use** — shell, files, web search, and persistent memory, gated by a policy engine
- **Session persistence** — conversations survive daemon restarts
- **Progressive feedback** — spoken fillers and notifications during long LLM calls
- **User scripts** — custom voice-triggered commands that bypass the LLM
- **Web widget** — follow the conversation and confirm tool calls in your browser
- **Android app** — voice/text turns, live transcript, remote confirmations, and background presence
- **Bilingual** — English and Spanish across the desktop UI and the Android app
- **Two backends** — OpenCode CLI (default) or a native loop against a local model

## Three ways to use it

The same daemon and conversation are reachable three ways — they cover different situations rather than replacing each other:

| Interface | When it fits |
|---|---|
| **Hotkey** (`Alt+Z`) | Quick, hands-on-keyboard questions with a short spoken answer |
| **[Web widget](how-to/web-widget.md)** | Reading long answers, copying a command, watching tools run and approving them |
| **[Android app](tutorial/mobile-app.md)** | Driving the PC from across the room and approving sensitive actions remotely |

A turn started by voice shows up in the widget and the app; a turn typed on the phone is spoken by the PC. See [Interfaces and use cases](explanation/use-cases.md) for concrete scenarios.

## Download

- **Source / installer**: [github.com/JosLuna1098/mirach](https://github.com/JosLuna1098/mirach)
- **Android app**: [latest release](https://github.com/JosLuna1098/mirach/releases/latest) ([all releases](https://github.com/JosLuna1098/mirach/releases))

## Documentation structure

This documentation follows the [Diátaxis framework](https://diataxis.fr/):

| Section | Purpose |
|---|---|
| **[Tutorial](tutorial/get-started.md)** | Learn by doing — install and have your first conversation |
| **[How-to Guides](how-to/user-scripts.md)** | Solve specific problems — add scripts, change voices, troubleshoot |
| **[Reference](reference/configuration.md)** | Technical details — configuration, architecture, the HTTP/SSE API |
| **[Explanation](explanation/design-decisions.md)** | Understand the why — design decisions and tradeoffs |

## Requirements

- **Linux desktop** (Wayland or X11 with `notify-send`)
- **Python 3.11+**
- **NVIDIA GPU with CUDA 12** (CPU mode works with higher latency)
- **A microphone**
- **Android 8.0+** (optional, for the companion app)

## Next steps

- Follow the [Get Started tutorial](tutorial/get-started.md) to install and configure Mirach
- Set up the [Android app](tutorial/mobile-app.md) to drive Mirach from your phone
- Read the [architecture reference](reference/architecture.md) to understand the design
- Browse the [configuration reference](reference/configuration.md) to tune every setting

## Inspiration

This project was inspired by Nate Gentile's video [Mi PC Linux ahora trabaja por mí (CachyOS + IA)](https://www.youtube.com/watch?v=b6uQTR7E9qg).
