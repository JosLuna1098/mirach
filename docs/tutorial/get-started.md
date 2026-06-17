# Tutorial: Get Started with Mirach

This tutorial will walk you through installing Mirach, configuring your first voice assistant, and having your first conversation. By the end, you'll understand the basic workflow: press a hotkey, talk, and get a spoken response.

## What you'll learn

- How to install Mirach on your system
- How to configure your assistant's personality
- How to use the hotkey to start and stop recording
- How conversations are saved and viewed

## Prerequisites

- **Linux desktop** (tested on CachyOS + Hyprland; any Wayland/X11 desktop with `notify-send` works)
- **Python 3.11+**
- **NVIDIA GPU with CUDA 12 drivers** (CPU mode works but adds 2-5s latency)
- **A microphone**

## Step 1: Install Mirach

Run the installer from your terminal:

```bash
git clone https://github.com/JosLuna1098/mirach ~/mirach && python3 ~/mirach/install.py
```

The interactive wizard will guide you through:

1. **GPU detection** — automatically detects CUDA and sets the right Whisper device
2. **Assistant name** — what your assistant will be called (e.g., "Mirach", "Aria", "Nexus")
3. **Language** — choose English or Spanish for UI strings and filler phrases
4. **Whisper model** — `medium` (multilingual) or `medium.en` (English-optimized)
5. **Piper voice download** — selects and downloads a voice model for text-to-speech
6. **Obsidian vault path** — optional, for persistent memory across sessions
7. **OpenCode CLI** — checks for or installs the LLM backend
8. **System prompt generation** — creates your personalized `system_prompt.md`
9. **Skill installation** — installs OpenCode skills for extended capabilities
10. **Systemd service** — creates and starts the user service

If you want to accept all defaults without interaction:

```bash
python3 ~/mirach/install.py --yes
```

### After installation

Mirach uses the `opencode_serve` backend by default. Configure your LLM provider with:

```bash
opencode auth
```

If you prefer a fully local setup, switch to the `native` backend and point it at a local Ollama model — see the [configuration reference](../reference/configuration.md#native-backend).

### Local configuration with mirach.env

Settings live in `mirach.env` at the project root (loaded automatically by `run_daemon.sh`). The installer creates it for you. A typical file:

```bash
MIRACH_VOICE=daniela.onnx
MIRACH_LOCALE=es
MIRACH_WHISPER_LANG=es
MIRACH_SERVER_HOST=0.0.0.0
```

`MIRACH_SERVER_HOST=0.0.0.0` makes the HTTP server reachable from the [Android app](mobile-app.md). See the [configuration reference](../reference/configuration.md) for every variable.

## Step 2: Understand the hotkey workflow

Mirach uses a single hotkey (default: `Alt+Z`) for all interactions. The hotkey is bound during installation. Here's how it works:

### First press: Start recording

1. Press `Alt+Z`
2. You hear a **short high beep** (1320 Hz)
3. A desktop notification appears: "🎤 Listening..."
4. Start talking — the microphone is now recording

### Second press: Process and respond

1. Press `Alt+Z` again when you're done speaking
2. You hear a **short low beep** (660 Hz)
3. Mirach transcribes your speech, queries the LLM, and speaks the answer
4. A notification shows what you said and the assistant's response

### Third press (during processing or speaking): Interrupt

1. Press `Alt+Z` while Mirach is thinking or speaking
2. The current response is **interrupted immediately**
3. You hear the high beep again — start a new recording

This means the same keypress does three different things depending on the current state.

## Step 3: Have your first conversation

Try asking something simple:

> "What's the weather today?"

Or in Spanish:

> "¿Qué hora es?"

You should hear:
1. The low beep when you press the hotkey to finish
2. A processing notification
3. If the LLM takes more than 10 seconds, a notification appears
4. If it takes more than 30 seconds, you hear "Still working on it..." (or the Spanish equivalent)
5. The spoken response

## Step 4: View your conversation

After your first exchange, say one of these phrases:

- **English**: "show conversation", "view conversation", "read the conversation"
- **Spanish**: "muéstrame la conversación", "ver conversación", "lee la conversación"

Mirach will generate a styled HTML page and open it in your browser. The page shows your conversation in a chat-style layout with dark theme.

You can also find the raw Markdown file at:

```
~/mirach/logs/conversations/latest.md
```

Each session creates a new timestamped file, and `latest.md` is a symlink to the most recent one.

## Step 5: Customize your assistant

Your assistant's personality is defined in `system_prompt.md`. Edit it to change how your assistant behaves:

```bash
$EDITOR ~/mirach/system_prompt.md
```

After editing, restart the daemon:

```bash
systemctl --user restart mirach
```

The system prompt controls:
- Language and tone
- Response length (important for TTS — keep it short)
- Whether to confirm before destructive actions
- How to use skills and tools

## What's next?

- Set up the [Android companion app](mobile-app.md) to drive Mirach from your phone
- **How-to guides** for specific tasks: adding user scripts, changing voices, troubleshooting
- **Reference** for all configuration options, the architecture, and the HTTP/SSE API
- **Explanation** of the design decisions behind Mirach

## Common issues during setup

**"Daemon is not running" notification when pressing the hotkey**

Start the daemon:

```bash
systemctl --user start mirach
```

**No sound from the speaker**

Check that your Piper voice was downloaded correctly:

```bash
ls ~/mirach/voices/
```

You should see at least one `.onnx` file.

**Microphone not detected**

List available microphones:

```bash
~/mirach/venv/bin/python -c "import sounddevice as sd; print(sd.query_devices())"
```

Then set `MIRACH_MIC` to a substring of your mic name in the systemd service file.
