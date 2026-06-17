# How to troubleshoot

## Daemon won't start

```bash
# Check service status
systemctl --user status mirach

# View full logs
journalctl --user -u mirach --no-pager -n 50
```

Common causes:
- OpenCode not installed or not authenticated
- Piper voice file missing from `voices/`
- Microphone not detected

## CUDA errors

```bash
# Test CUDA availability
~/mirach/venv/bin/python -c "import torch; print(torch.cuda.is_available())"

# Fall back to CPU
systemctl --user edit mirach
# Add: Environment=MIRACH_WHISPER_DEVICE=cpu
# Add: Environment=MIRACH_WHISPER_COMPUTE=int8
```

## `Could not load library libcudnn_ops.so.9`

faster-whisper needs CUDA 12 runtime libraries. They're installed via pip but live inside the venv. The `run_daemon.sh` script adds them to `LD_LIBRARY_PATH` automatically.

If you're using systemd, the service file should use `ExecStart=%h/mirach/run_daemon.sh` (not `python -m mirach` directly).

## OpenCode not responding

```bash
# Test OpenCode directly
opencode run "hello"

# Check authentication
opencode auth
```

The default backend (`opencode_serve`) spawns and supervises an `opencode serve` subprocess. If turns hang, confirm the `opencode` binary is on `PATH` and authenticated. The provider and model come from opencode's own config unless you override them with `MIRACH_OPENCODE_SERVE_PROVIDER_ID` / `MIRACH_OPENCODE_SERVE_MODEL_ID`.

## "Daemon is not running" notification

```bash
# Start the daemon
systemctl --user start mirach

# Check if the socket exists
ls -la /tmp/mirach.sock
```

## Mic not detected

```bash
# List available audio devices
~/mirach/venv/bin/python -c "import sounddevice as sd; print(sd.query_devices())"

# Set MIRACH_MIC to a substring of your mic name
systemctl --user edit mirach
# Add: Environment=MIRACH_MIC=your-mic-name
```

## No sound from speaker

```bash
# Check voice files exist
ls ~/mirach/voices/

# Test Piper directly
~/mirach/venv/bin/python -c "
from piper import PiperVoice
voice = PiperVoice.load('voices/your-voice.onnx')
voice.synthesize_wav('Hello world', open('/tmp/test.wav', 'wb'))
"
aplay /tmp/test.wav
```

## Session not persisting

```bash
# Check if session ID is cached
cat ~/.cache/mirach/session_id

# Clear and start fresh
rm ~/.cache/mirach/session_id
systemctl --user restart mirach
```

## High VRAM usage

```bash
# Check current VRAM
nvidia-smi

# Switch to smaller model
systemctl --user edit mirach
# Add: Environment=MIRACH_WHISPER_MODEL=small
# Add: Environment=MIRACH_WHISPER_COMPUTE=int8
```

## LLM takes too long

Pick a faster model in opencode's config (or override it). For the `opencode_serve` backend:

```bash
systemctl --user edit mirach
# Add: Environment=MIRACH_OPENCODE_SERVE_MODEL_ID=deepseek-v4-flash-free
```

For the `native` backend, the request timeout is `MIRACH_NATIVE_TIMEOUT` (default 120s):

```bash
# Add: Environment=MIRACH_NATIVE_TIMEOUT=180
```

## Phone can't connect to the daemon

```bash
# The server binds 127.0.0.1 by default — the phone can't reach loopback.
# Bind all interfaces in mirach.env:
echo "MIRACH_SERVER_HOST=0.0.0.0" >> ~/mirach/mirach.env
systemctl --user restart mirach
```

Then check the phone is on the same network (LAN or Tailscale) and use the PC's IP, not `127.0.0.1`. The pairing code is printed in the daemon logs at startup. See the [Android app tutorial](../tutorial/mobile-app.md).
