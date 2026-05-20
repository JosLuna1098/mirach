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

Set the `MIRACH_VOICE` environment variable in your systemd service:

```bash
systemctl --user edit mirach
```

Add:

```ini
[Service]
Environment=MIRACH_VOICE=en_US-lessac-medium.onnx
```

Then restart:

```bash
systemctl --user restart mirach
```

## Adjust voice speed

The `MIRACH_VOICE_SPEED` variable controls the `length_scale` parameter:

- `>1` = slower speech
- `<1` = faster speech
- Default is `1.2`

```ini
[Service]
Environment=MIRACH_VOICE_SPEED=1.0
```
