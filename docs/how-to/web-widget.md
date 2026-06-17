# How to use the web widget

The web widget is a browser interface to the running daemon. It shows the live conversation, lets you send text turns, toggle reasoning, stop the current turn, and approve or deny tool calls — without touching the hotkey.

## Open the widget

With the daemon running, open this URL in a browser on the **same machine**:

```
http://127.0.0.1:7270
```

That's it — no token to enter. The widget is served only to loopback (`127.0.0.1`) and authenticates itself with an internal token injected into the page at serve time.

!!! note
    The widget is loopback-only by design. A remote browser gets a `403`. To drive Mirach from another device, use the [Android app](../tutorial/mobile-app.md), which talks to the JSON API instead.

## What it shows

- **Live transcript** — your turns, the assistant's streaming answer, tool calls, and tool results
- **Reasoning toggle** (🧠) — show or hide the model's reasoning blocks
- **Text input** — type a message and send it, exactly like speaking a turn
- **Stop button** — interrupt the current turn
- **Confirm / Deny** — when a tool needs approval, buttons appear inline

The widget subscribes to the same `ConversationBus` event stream as the desktop pipeline and the mobile app, so everything stays in sync: a turn started by voice appears in the widget, and a turn typed in the widget is spoken by the PC.

## Change the port

The widget follows `MIRACH_SERVER_PORT` (default `7270`):

```bash
# mirach.env
MIRACH_SERVER_PORT=8080
```

Then open `http://127.0.0.1:8080`.

## Disable the server

If you don't want the HTTP server (and therefore the widget or the app):

```bash
# mirach.env
MIRACH_SERVER_ENABLED=0
```
