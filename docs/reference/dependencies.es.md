# Referencia de dependencias

## Dependencias de ejecución

| Paquete | Versión | Propósito |
|---|---|---|
| `faster-whisper` | >=1.2.1, <2.0 | Reconocimiento de voz vía CTranslate2 (motor Whisper) |
| `piper-tts` | >=1.4.2, <2.0 | Síntesis de voz neuronal local |
| `pyyaml` | >=6.0, <7.0 | Parsea `policy.yaml` (reglas de permisos de herramientas) |
| `sounddevice` | >=0.5.5, <1.0 | E/S de audio — captura de micrófono y reproducción por altavoz |
| `numpy` | >=2.4.6, <3.0 | Operaciones numéricas para el procesamiento de audio |

El servidor HTTP/SSE usa únicamente la librería estándar de Python (`http.server`) — sin dependencia de ningún framework web.

## Dependencias opcionales

| Paquete | Versión | Propósito |
|---|---|---|
| `scipy` | >=1.17.1 | Remuestreo polifásico de alta calidad para la reducción de Whisper. Recurre a un filtro boxcar si no está instalado. |

Instala con: `pip install -e ".[quality]"`

## Dependencias de desarrollo

| Paquete | Versión | Propósito |
|---|---|---|
| `pytest` | >=9.0.3 | Framework de pruebas |
| `ruff` | >=0.15.13 | Linting y formateo |

Instala con: `pip install -e ".[dev]"`

## Dependencias del sistema

| Paquete | Propósito | Requerido |
|---|---|---|
| PortAudio | Backend de audio para sounddevice | Sí (preinstalado en la mayoría de escritorios Linux) |
| Drivers CUDA 12 | Aceleración por GPU para Whisper | Sí para modo GPU |
| `nvidia-cublas-cu12` | Librería CUDA 12 BLAS (vía pip) | Sí para modo GPU |
| `nvidia-cudnn-cu12` | Librería CUDA 12 DNN (vía pip) | Sí para modo GPU |
| `notify-send` | Notificaciones de escritorio (libnotify) | Opcional |
| `xdg-open` | Abrir URLs en el navegador por defecto | Opcional (para el visor de conversaciones) |

## Dependencias externas (no en pyproject.toml)

| Componente | Propósito | Instalación |
|---|---|---|
| OpenCode CLI | Backend del LLM | Instalado por `install.py` o manualmente |
| Modelos de voz Piper | Datos de voz para TTS | Descargados por `install.py` desde Hugging Face |
| Pesos del modelo Whisper | Datos del modelo STT | Descargados automáticamente por faster-whisper en el primer uso |

## Ruta de librerías CUDA

CTranslate2 (usado por faster-whisper) requiere librerías de ejecución de CUDA 12. Estas se instalan vía pip dentro del `site-packages` del venv, no en la ruta de librerías del sistema. El script `run_daemon.sh` las añade a `LD_LIBRARY_PATH`:

```bash
export LD_LIBRARY_PATH="$SITE/nvidia/cublas/lib:$SITE/nvidia/cudnn/lib:${LD_LIBRARY_PATH:-}"
```

Por eso debes usar `run_daemon.sh` (o definir `LD_LIBRARY_PATH` en tu archivo de servicio) en vez de ejecutar `python -m mirach` directamente para el modo GPU.
