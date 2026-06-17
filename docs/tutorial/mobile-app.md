# Tutorial: Android companion app

The Mirach Android app is a remote control for the PC daemon. It lets you send voice or text turns, see the full conversation transcript, approve or deny tool calls, and follow along while Mirach works — all from your phone.

## What you'll need

- An Android phone (Android 8.0+, arm64 recommended)
- The PC daemon running with `MIRACH_SERVER_HOST=0.0.0.0` so the phone can reach it
- Both devices on the same network (LAN or [Tailscale](https://tailscale.com))

## Step 1: Install the APK

Download the latest APK from the [Releases page](https://github.com/JosLuna1098/mirach/releases/latest).

Choose `app-arm64-v8a-release.apk` for any modern Android phone (2018+). Install it:

1. Transfer the APK to your phone
2. Open it — Android will ask you to allow installing from unknown sources
3. Accept and install

## Step 2: Start the daemon with network access

On your PC, start the daemon so it listens on all interfaces:

```bash
./run_daemon.sh
```

If `MIRACH_SERVER_HOST=0.0.0.0` is set in your `mirach.env` (the default after installation) the daemon is reachable over the network. The logs will show:

```
Pairing code: XXXXXX
```

Note the pairing code — you'll need it in the next step.

## Step 3: Pair the app

1. Open the Mirach app on your phone
2. Enter your PC's IP address and port: `192.168.x.x:7270`
   - If using Tailscale, enter the Tailscale IP (`100.x.x.x:7270`)
3. Enter the pairing code from the daemon logs
4. Tap **Connect**

The app stores the token and reconnects automatically on future opens. The code rotates after each successful pairing.

## Features

### Voice input (STT)

Tap the microphone button to start recording. Tap again to send. Long-press for push-to-talk (hold to record, release to send).

With auto-send enabled, a 3-second countdown gives you time to edit the transcription before it's sent automatically.

### Text input

Type directly in the input field and tap **Send**.

### Turn control

- **Interrupt** — interrupts the current turn and sends a new one
- **Clear queue** — discards all pending turns in the queue; the current turn continues
- **New conversation** — closes the session and starts fresh

### Conversation transcript

The app shows a live transcript: your turns, the assistant's answer, tool calls and results, and confirmation requests. Reasoning blocks (when visible) appear as collapsible sections.

### Approve / deny tool calls

When Mirach needs to run a tool that requires confirmation, a card appears in the transcript with **Approve** and **Deny** buttons. You can also deny from the notification (when the app is in the background).

### Background presence

When you leave the app, a foreground notification keeps the connection alive and shows Mirach's current state:

- **Tap to return** — idle
- **Mirach is working…** — processing a turn
- **⚠ Confirm: \<tool\>** — waiting for your approval (tap **Approve** / **Deny** from the notification)
- **⚠ Mirach — error** — an error occurred

### Read response (TTS)

The app can read Mirach's answers aloud using the phone's native TTS. Three modes:

| Mode | Behavior |
|---|---|
| Auto | Reads only if the turn was sent via voice input |
| Always | Reads every response |
| Never | No reading |

### Language

The app UI and notification strings follow the language set in the settings popover (English or Spanish). The setting persists across restarts.

## Settings popover

Tap ⋮ in the top-right corner to open settings:

| Setting | Description |
|---|---|
| Auto-send voice | Send the transcription automatically after a countdown |
| Show reasoning | Display reasoning blocks in the transcript |
| Show tool calls | Display tool call cards |
| Show tool results | Display tool result cards (collapsed by default) |
| Read response | TTS mode: Auto / Always / Never |
| Language | App UI and notification language (English / Español) |
| Disconnect from PC | Forget the current token and go back to the pairing screen |

## Network requirements

The app communicates directly with the PC's HTTP server. No cloud relay is used.

- **Same LAN**: enter the PC's local IP (e.g. `192.168.1.10:7270`)
- **Over Tailscale**: enter the PC's Tailscale IP (e.g. `100.64.x.x:7270`)
- **Port 7270** must be reachable from the phone to the PC
