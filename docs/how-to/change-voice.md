# How to change the Piper voice

## Download a new voice

Browse available voices at [rhasspy/piper-voices on Hugging Face](https://huggingface.co/rhasspy/piper-voices/tree/main).

Download the `.onnx` and `.onnx.json` files to `~/mirach/voices/`:

```bash
cd ~/mirach/voices
curl -L -o en_US-lessac-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
curl -L -o en_US-lessac-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

## Configure the voice

Set `MIRACH_VOICE` to the new filename. Edit `mirach.env` at the project root:

```bash
MIRACH_VOICE=en_US-lessac-medium.onnx
```

Or, if you run via systemd, add it to the service:

```bash
systemctl --user edit mirach
```

```ini
[Service]
Environment=MIRACH_VOICE=en_US-lessac-medium.onnx
```

Then restart:

```bash
systemctl --user restart mirach
# or, if launching manually:
./run_daemon.sh
```

## Adjust voice speed

The `MIRACH_VOICE_SPEED` variable controls the `length_scale` parameter:

- `>1` = slower speech
- `<1` = faster speech
- Default is `1.2`

```bash
# mirach.env
MIRACH_VOICE_SPEED=1.0
```
