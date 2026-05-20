# IPC Protocol Reference

The daemon communicates with external clients via a Unix domain socket.

## Socket path

Default: `/tmp/mirach.sock`

Override with `MIRACH_SOCKET` environment variable.

## Protocol

Simple text-based, one message per connection. The client connects, sends a message, and disconnects.

### Messages

| Message | Response | Description |
|---|---|---|
| `toggle` | _(none)_ | Triggers the FSM state transition (IDLE → RECORDING → PROCESSING → IDLE) |
| `ping` | `pong` | Health check — returns immediately |

### Example: sending a toggle

```python
import socket

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect("/tmp/mirach.sock")
s.sendall(b"toggle")
s.close()
```

### Example: health check

```python
import socket

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(2)
s.connect("/tmp/mirach.sock")
s.sendall(b"ping")
response = s.recv(64).decode()  # "pong"
s.close()
```

## Error handling

If the socket doesn't exist or the connection is refused, the daemon is not running. The `trigger.py` script handles this by showing a desktop notification.

## Security

The socket is created in `/tmp/` with default permissions. On a multi-user system, consider setting `MIRACH_SOCKET` to a path in a private directory.
