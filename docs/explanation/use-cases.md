# Interfaces and use cases

Mirach has three interfaces to the same daemon. They are not alternatives to pick once — they cover different situations, and most users move between them during a normal day.

| Interface | Input | Output | Reach | Best for |
|---|---|---|---|---|
| **Hotkey** (`Alt+Z`) | Voice | Spoken | At the keyboard | Quick hands-on-keyboard questions |
| **Web widget** | Text | Spoken (PC) + on-screen | Same machine, browser | Reading long answers, copying output, watching tools run |
| **Android app** | Voice + text | On-screen + optional phone TTS | Any device on the network | Away from the desk, approving actions remotely |

All three share one conversation and one session. A turn you start by voice shows up in the widget and the app; a turn you type on the phone is spoken by the PC. Nothing is siloed.

## Why not just the hotkey?

The hotkey is the fastest path when you're sitting at the machine and the answer is short. It breaks down in three common situations:

1. **The answer is long or structured.** Spoken output is linear and gone the moment it finishes. A command, a list, a block of code, or a path is painful to consume by ear.
2. **You're not at the desk.** The hotkey lives on the PC. If you're across the room or in another part of the house, you can't press it — and you can't hear a confirmation prompt.
3. **A tool needs approval and you're away.** The policy engine pauses on sensitive actions and waits. If nobody's there to confirm, the turn stalls.

The widget solves (1). The app solves (2) and (3). Below are concrete scenarios.

## Use cases for the web widget

### Reading and copying output

You ask Mirach to summarize a log or generate a shell command. Hearing a 200-character command read aloud is useless — but the widget shows it on screen, where you can read it carefully and copy it into your terminal. The PC still speaks the answer, so you get both channels at once.

### Watching an agentic task unfold

When Mirach runs tools (shell, file edits, web search), the widget streams each `tool_call` and `tool_result` as a card. You see exactly what it ran and what came back, instead of inferring it from a spoken summary. This makes the policy engine's confirmations meaningful: you can read the command before approving it.

### Following reasoning

Toggle the 🧠 reasoning view to watch the model's thinking on longer tasks, then hide it again for clean answers. Useful when you're debugging a prompt or checking whether the assistant understood a tricky request.

### A quiet channel

In a meeting or a shared space, you can type a turn in the widget instead of speaking. The answer is still spoken on the PC — but you can mute the speakers and read it instead.

## Use cases for the Android app

### Driving the PC from across the room

You're on the couch and want the PC to do something — start a task, check a status, run a script. The app sends the turn over the network; the PC executes and speaks. No need to walk to the keyboard.

### Approving actions remotely

Mirach is working on a long task and hits a step the policy engine gates — say, deleting files or running a privileged command. Instead of the turn stalling until you're back at the desk, the app raises a notification with **Approve** / **Deny** buttons. You decide from your phone, even with the app in the background, and the task continues.

### Voice from the phone

The app does on-device speech-to-text, so you can speak a turn into the phone and have it transcribed and sent without being at the PC mic. With "read response" on, the phone reads the answer back too — handy when the PC speakers are off or you're out of earshot.

### Staying informed in the background

When you leave the app, a foreground notification keeps the connection alive and reflects the current state — idle, working, waiting for confirmation, or error. You always know whether Mirach is busy or stuck without reopening the app.

### A second screen for a long answer

Same idea as the widget's read-and-copy case, but anywhere: a long answer or a generated command lands as selectable text on the phone, ready to read or share.

## Picking an interface

- **Short, hands-on-keyboard question** → hotkey
- **Long answer, code, or a command you'll copy** → widget (or app)
- **Watching tools run / approving a sensitive command at the desk** → widget
- **Away from the desk, or approving actions remotely** → app
- **Quiet environment** → widget or app (type instead of speak)
