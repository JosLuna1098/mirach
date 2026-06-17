# Cómo solucionar problemas

## El daemon no arranca

```bash
# Revisar el estado del servicio
systemctl --user status mirach

# Ver los logs completos
journalctl --user -u mirach --no-pager -n 50
```

Causas comunes:
- OpenCode no instalado o no autenticado
- Falta el archivo de voz Piper en `voices/`
- Micrófono no detectado

## Errores de CUDA

```bash
# Probar la disponibilidad de CUDA
~/mirach/venv/bin/python -c "import torch; print(torch.cuda.is_available())"

# Recurrir a CPU
systemctl --user edit mirach
# Añade: Environment=MIRACH_WHISPER_DEVICE=cpu
# Añade: Environment=MIRACH_WHISPER_COMPUTE=int8
```

## `Could not load library libcudnn_ops.so.9`

faster-whisper necesita las librerías de ejecución de CUDA 12. Se instalan vía pip pero viven dentro del venv. El script `run_daemon.sh` las añade a `LD_LIBRARY_PATH` automáticamente.

Si usas systemd, el archivo de servicio debe usar `ExecStart=%h/mirach/run_daemon.sh` (no `python -m mirach` directamente).

## OpenCode no responde

```bash
# Probar OpenCode directamente
opencode run "hola"

# Revisar la autenticación
opencode auth
```

El backend por defecto (`opencode_serve`) lanza y supervisa un subproceso `opencode serve`. Si los turnos se cuelgan, confirma que el binario `opencode` está en el `PATH` y autenticado. El proveedor y el modelo vienen de la propia config de opencode salvo que los sobrescribas con `MIRACH_OPENCODE_SERVE_PROVIDER_ID` / `MIRACH_OPENCODE_SERVE_MODEL_ID`.

## Notificación "El daemon no está corriendo"

```bash
# Arrancar el daemon
systemctl --user start mirach

# Verificar que el socket existe
ls -la /tmp/mirach.sock
```

## Micrófono no detectado

```bash
# Listar dispositivos de audio disponibles
~/mirach/venv/bin/python -c "import sounddevice as sd; print(sd.query_devices())"

# Definir MIRACH_MIC con una subcadena del nombre de tu micrófono
systemctl --user edit mirach
# Añade: Environment=MIRACH_MIC=nombre-de-tu-micro
```

## Sin sonido del altavoz

```bash
# Verificar que los archivos de voz existen
ls ~/mirach/voices/

# Probar Piper directamente
~/mirach/venv/bin/python -c "
from piper import PiperVoice
voice = PiperVoice.load('voices/tu-voz.onnx')
voice.synthesize_wav('Hola mundo', open('/tmp/test.wav', 'wb'))
"
aplay /tmp/test.wav
```

## La sesión no persiste

```bash
# Verificar si el ID de sesión está en caché
cat ~/.cache/mirach/session_id

# Limpiar y empezar de cero
rm ~/.cache/mirach/session_id
systemctl --user restart mirach
```

## Uso alto de VRAM

```bash
# Revisar la VRAM actual
nvidia-smi

# Cambiar a un modelo más pequeño
systemctl --user edit mirach
# Añade: Environment=MIRACH_WHISPER_MODEL=small
# Añade: Environment=MIRACH_WHISPER_COMPUTE=int8
```

## El LLM tarda demasiado

Elige un modelo más rápido en la config de opencode (o sobrescríbelo). Para el backend `opencode_serve`:

```bash
systemctl --user edit mirach
# Añade: Environment=MIRACH_OPENCODE_SERVE_MODEL_ID=deepseek-v4-flash-free
```

Para el backend `native`, el timeout de la petición es `MIRACH_NATIVE_TIMEOUT` (por defecto 120s):

```bash
# Añade: Environment=MIRACH_NATIVE_TIMEOUT=180
```

## El teléfono no se conecta al daemon

```bash
# El servidor hace bind a 127.0.0.1 por defecto — el teléfono no alcanza loopback.
# Haz bind a todas las interfaces en mirach.env:
echo "MIRACH_SERVER_HOST=0.0.0.0" >> ~/mirach/mirach.env
systemctl --user restart mirach
```

Luego verifica que el teléfono está en la misma red (LAN o Tailscale) y usa la IP de la PC, no `127.0.0.1`. El código de emparejamiento se imprime en los logs del daemon al inicio. Consulta el [tutorial de la app de Android](../tutorial/mobile-app.md).
