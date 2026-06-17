# Cómo cambiar la voz de Piper

## Descarga una nueva voz

Explora las voces disponibles en [rhasspy/piper-voices en Hugging Face](https://huggingface.co/rhasspy/piper-voices/tree/main).

Descarga los archivos `.onnx` y `.onnx.json` a `~/mirach/voices/`:

```bash
cd ~/mirach/voices
curl -L -o en_US-lessac-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
curl -L -o en_US-lessac-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

## Configura la voz

Define `MIRACH_VOICE` con el nuevo nombre de archivo. Edita `mirach.env` en la raíz del proyecto:

```bash
MIRACH_VOICE=en_US-lessac-medium.onnx
```

O, si corres vía systemd, añádelo al servicio:

```bash
systemctl --user edit mirach
```

```ini
[Service]
Environment=MIRACH_VOICE=en_US-lessac-medium.onnx
```

Luego reinicia:

```bash
systemctl --user restart mirach
# o, si lo lanzas manualmente:
./run_daemon.sh
```

## Ajusta la velocidad de la voz

La variable `MIRACH_VOICE_SPEED` controla el parámetro `length_scale`:

- `>1` = habla más lenta
- `<1` = habla más rápida
- El valor por defecto es `1.2`

```bash
# mirach.env
MIRACH_VOICE_SPEED=1.0
```
