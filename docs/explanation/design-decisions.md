# Design Decisions

This document explains the key architectural choices behind Mirach.

## Local-first STT and TTS, cloud LLM

Mirach keeps speech-to-text and text-to-speech local (Whisper and Piper) but uses a cloud LLM via OpenCode. This balances:

- **Privacy**: Voice recordings never leave your machine. Only the transcribed text is sent to the LLM.
- **Speed**: Local STT and TTS have ~0.5s latency each, independent of network conditions.
- **Intelligence**: Cloud LLMs provide capabilities that local models can't match (yet).

For fully local operation, you can point OpenCode to a local Ollama instance.

## Daemon architecture

Models stay in RAM permanently. The alternative — loading Whisper and Piper on every invocation — would add 3-7 seconds of cold-start latency per interaction.

## Single hotkey, three states

One key for record, process, and interrupt. This matches how people actually use voice assistants: you want to interrupt a wrong response and immediately say something different, without reaching for a second button.

## Whisper medium + int8

The original setup used `large-v3-turbo` with `float16` (~2.3 GB VRAM). The switch to `medium` with `int8` (~700 MB VRAM) trades 0.2s of transcription speed for 1.6 GB of VRAM savings — a worthwhile trade since the LLM call takes seconds anyway.

## User scripts over hardcoded patterns

Custom voice commands live in a gitignored `user_scripts/` directory with metadata comments. This makes triggers personal (not in the repo), extensible (just add a file), and self-documenting.

## Progressive feedback

During long LLM calls, escalating feedback (fillers → notifications → "still working" messages) prevents users from thinking the daemon has crashed. Fillers are pre-baked as WAV files for zero-latency playback.

## Markdown conversation logs

Conversations are saved as Markdown, not JSON or a database. This makes them human-readable, git-friendly, and compatible with any Markdown tool. The `latest.md` symlink provides quick access.

## Session persistence

The OpenCode session ID is saved to disk so conversations survive daemon restarts and system reboots. A 1-hour idle timeout ensures stale sessions eventually expire.
