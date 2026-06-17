# HTTP/SSE API Reference

The daemon exposes a local HTTP server (enabled by default on port 7270) that powers the browser widget and the Android companion app. All endpoints except `/pair` require a device token.

## Authentication

Pass the token in either form:

- Query string: `?token=<token>`
- Header: `Authorization: Bearer <token>`

A missing or invalid token returns `401 Unauthorized`.

## Pairing

```
POST /pair
```

Exchanges a one-time pairing code (printed in the daemon logs at startup) for a long-lived device token. No auth required.

**Request body:**
```json
{ "code": "XXXXXX", "device": "My Phone" }
```

**Response:**
```json
{ "token": "<long-lived-token>" }
```

The pairing code rotates after each successful use. Restart the daemon or check the logs for a new code.

## SSE event stream

```
GET /events?token=<token>&since=<n>
```

Opens a persistent Server-Sent Events stream. Each frame is:

```
data: <json>\n\n
```

Heartbeat frames (keep-alive):

```
:\n\n
```

The `since` parameter is the number of events already received. On reconnect, pass the count to replay missed events.

### Event types

| Type | Description |
|---|---|
| `queued` | A new turn was accepted into the queue. `{ type, text, position }` |
| `queue_cleared` | The pending queue was cleared. `{ type }` |
| `user_turn` | The LLM started processing a turn. `{ type, text }` |
| `text_delta` | Incremental response text. `{ type, delta }` |
| `tool_call` | A tool was invoked. `{ type, tool_call_id, name, arguments }` |
| `tool_result` | A tool returned a result. `{ type, tool_call_id, content, is_error }` |
| `awaiting_confirmation` | A tool is waiting for the user to approve/deny. `{ type, tool_call_id, name, arguments }` |
| `done` | The turn is complete. `{ type, content }` — `content` is the final clean answer. |
| `error` | An error occurred. `{ type, message }` |
| `cost` | Token usage for the turn. `{ type, input_tokens, output_tokens }` |

## Turn input

```
POST /turn
```

**Request body:**
```json
{
  "text": "What's the weather today?",
  "interrupt": false,
  "clear_queue": false
}
```

- `interrupt: true` — interrupt the running turn and optionally the queue before processing this one.
- `clear_queue: true` — discard all queued turns (does not interrupt the current turn).

**Response:**
```json
{ "status": "queued", "position": 1 }
```

## Stop

```
POST /stop
```

Stops the current turn and TTS immediately. Equivalent to pressing the hotkey during processing.

**Response:** `{ "status": "ok" }`

## Confirm / deny tool call

```
POST /confirm   { "tool_call_id": "<id>" }
POST /deny      { "tool_call_id": "<id>" }
```

Approve or reject a pending tool call. The `tool_call_id` comes from the `awaiting_confirmation` event.

**Response:** `{ "status": "ok" }`

## Close session

```
POST /close_session
```

Forces a new LLM session on the next turn (clears history).

**Response:** `{ "status": "ok" }`

## Clear queue

```
POST /clear_queue
```

Discards all queued turns. The current turn is unaffected.

**Response:** `{ "status": "ok" }`

## Web widget

```
GET /
```

Returns the embedded HTML widget. Only accessible from loopback (`127.0.0.1`); remote clients (mobile app) use the JSON API above.

## Binding for remote access

By default, the server binds to `127.0.0.1` (loopback only). To allow the Android app to connect over the network, set `MIRACH_SERVER_HOST=0.0.0.0` in `mirach.env`. The device token is the sole authentication gate.

!!! warning
    Exposing the server on `0.0.0.0` grants network access to every tool Mirach can run. Use Tailscale or a firewall to restrict access to trusted devices.
