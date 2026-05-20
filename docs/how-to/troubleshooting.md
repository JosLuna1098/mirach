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
opencode run --model opencode/deepseek-v4-flash-free "hello"

# Check authentication
opencode auth
```

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

```bash
# Increase timeout
systemctl --user edit mirach
# Add: Environment=MIRACH_OPENCODE_TIMEOUT=180

# Or switch to a faster model
# Add: Environment=MIRACH_OPENCODE_MODEL=opencode/deepseek-v4-flash-free
```
