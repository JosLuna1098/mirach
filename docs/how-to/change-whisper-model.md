# How to change the Whisper model

## Available models

| Model | Size | VRAM (int8) | Speed | Notes |
|---|---|---|---|---|
| `medium` | 1.5 GB | ~700 MB | ~0.5s | Multilingual, recommended default |
| `medium.en` | 1.5 GB | ~700 MB | ~0.5s | English-optimized, slightly better for English |
| `large-v3-turbo` | 1.6 GB | ~2.3 GB (float16) | ~0.3s | Fastest but higher VRAM |
| `small` | 466 MB | ~300 MB | ~0.8s | Low VRAM, lower accuracy |

## Change the model

Edit your systemd service:

```bash
systemctl --user edit mirach
```

Add:

```ini
[Service]
Environment=MIRACH_WHISPER_MODEL=medium.en
Environment=MIRACH_WHISPER_COMPUTE=int8
```

Restart:

```bash
systemctl --user restart mirach
```

The model is downloaded automatically on first use.

## Compute type

| Compute | Device | VRAM | Accuracy |
|---|---|---|---|
| `int8` | cuda or cpu | Low | Good for speech |
| `float16` | cuda only | High | Maximum accuracy |
| `int8_float16` | cuda only | Medium | Hybrid approach |

For most users, `int8` on `cuda` is the best balance.
