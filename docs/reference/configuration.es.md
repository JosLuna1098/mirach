# Referencia de configuración

Todos los ajustes son variables de entorno `MIRACH_*` con valores por defecto razonables. Defínelas en `mirach.env` (cargado por `run_daemon.sh`) o como líneas `Environment=` en el servicio de systemd.

Precedencia (de mayor a menor): entorno del shell → `mirach.env` → valores por defecto integrados.

## Rutas

| Variable | Por defecto | Descripción |
|---|---|---|
| `MIRACH_BASE_DIR` | directorio del script | Raíz del proyecto. La resuelve automáticamente `run_daemon.sh`; cámbiala solo si logs/voices viven en otro lugar. |
| `MIRACH_SOCKET` | `/tmp/mirach.sock` | Ruta del socket Unix para el IPC de la tecla. |
| `MIRACH_SYSTEM_PROMPT` | `<BASE_DIR>/system_prompt.md` | Archivo del prompt de sistema del LLM. |

## Captura de audio

| Variable | Por defecto | Descripción |
|---|---|---|
| `MIRACH_MIC` | _(vacío)_ | Coincidencia por subcadena con el nombre del dispositivo de micrófono. Vacío = entrada por defecto del sistema. |
| `MIRACH_SAMPLE_RATE` | `48000` | Tasa de muestreo nativa del micrófono (Hz). La mayoría de micros USB: 48000. |
| `MIRACH_RMS_SILENCE` | `0.005` | Umbral RMS por debajo del cual el audio se descarta como silencio. |

## STT (Whisper)

| Variable | Por defecto | Descripción |
|---|---|---|
| `MIRACH_WHISPER_MODEL` | `medium` | Nombre del modelo. `medium` = multilingüe; `medium.en` = solo inglés. |
| `MIRACH_WHISPER_DEVICE` | `cuda` | `cuda` para GPU, `cpu` para solo CPU. |
| `MIRACH_WHISPER_COMPUTE` | `int8` | `float16` (GPU, más precisión) o `int8` (menos VRAM). |
| `MIRACH_WHISPER_LANG` | `es` | Código ISO 639-1 del idioma para transcripción (p. ej. `en`, `es`). |
| `MIRACH_WHISPER_BEAM_SIZE` | `3` | Tamaño de beam 1–5. Menor = más rápido, mayor = marginalmente más preciso. |

## TTS (Piper)

| Variable | Por defecto | Descripción |
|---|---|---|
| `MIRACH_VOICE` | `en_US-lessac-low.onnx` | Nombre del archivo de voz dentro de `voices/`. |
| `MIRACH_VOICE_SPEED` | `1.2` | `length_scale` de Piper. `>1` = más lento, `<1` = más rápido. |
| `MIRACH_VOICE_CONFIRM_TIMEOUT` | `20.0` | Segundos para esperar una respuesta de confirmación por voz antes de expirar. |

## Backend

| Variable | Por defecto | Descripción |
|---|---|---|
| `MIRACH_BACKEND` | `opencode_serve` | Backend del LLM: `opencode_serve` o `native`. |
| `MIRACH_SESSION_IDLE_TIMEOUT` | `3600` | Segundos de inactividad antes de reiniciar la sesión del LLM. |

### Backend opencode_serve

| Variable | Por defecto | Descripción |
|---|---|---|
| `MIRACH_OPENCODE_BIN` | `opencode` | Ruta o nombre del binario `opencode`. |
| `MIRACH_OPENCODE_SERVE_HOST` | `127.0.0.1` | Dirección donde escucha `opencode serve`. |
| `MIRACH_OPENCODE_SERVE_PORT` | `0` | Puerto de `opencode serve` (0 = puerto libre aleatorio). |
| `MIRACH_OPENCODE_SERVE_PROVIDER_ID` | _(vacío)_ | Proveedor a pasar a `opencode serve`. Vacío = el configurado en opencode. |
| `MIRACH_OPENCODE_SERVE_MODEL_ID` | _(vacío)_ | Modelo a pasar a `opencode serve`. Vacío = el configurado en opencode. |
| `MIRACH_OPENCODE_SERVE_STARTUP_TIMEOUT` | `15.0` | Segundos a esperar a que `opencode serve` imprima su URL antes de fallar. |
| `MIRACH_OPENCODE_SERVE_LOG` | _(vacío)_ | Define cualquier valor para pasar `--print-logs` a `opencode serve`. |

### Backend native

| Variable | Por defecto | Descripción |
|---|---|---|
| `MIRACH_NATIVE_BASE_URL` | `http://localhost:11434` | URL base del endpoint compatible con OpenAI (Ollama, llama.cpp, vLLM…). |
| `MIRACH_NATIVE_MODEL` | `qwen3:14b` | Nombre del modelo como lo conoce el proveedor. |
| `MIRACH_NATIVE_API_KEY` | `ollama` | Clave de API (usa `ollama` para Ollama, si no tu clave del proveedor). |
| `MIRACH_NATIVE_NUM_CTX` | `32768` | Tamaño de la ventana de contexto en tokens. |
| `MIRACH_NATIVE_TIMEOUT` | `120.0` | Timeout de la petición en segundos. |
| `MIRACH_NATIVE_TEMPERATURE` | `0.0` | Temperatura de muestreo. |
| `MIRACH_NATIVE_TOOL_PROTOCOL` | `auto` | Formato de llamadas de herramientas: `auto`, `native` o `prompted`. |
| `MIRACH_NATIVE_POLICY` | `<BASE_DIR>/policy.yaml` | Ruta al archivo de reglas de permisos de herramientas. |

## Compactación de contexto

| Variable | Por defecto | Descripción |
|---|---|---|
| `MIRACH_CONTEXT_STRATEGY` | `none` | Estrategia de compactación del historial: `none`, `sliding` o `summarize`. |
| `MIRACH_CONTEXT_MAX_TOKENS` | `32768` | Presupuesto de tokens antes de que la compactación entre en acción. |

## Idioma y retroalimentación al usuario

| Variable | Por defecto | Descripción |
|---|---|---|
| `MIRACH_LOCALE` | `en` | Idioma de la UI de escritorio (`en`, `es` o uno personalizado en `i18n.py`). |
| `MIRACH_HOTKEY` | `Alt+Z` | Etiqueta mostrada en notificaciones (cosmética; el binding real está en tu compositor). |
| `MIRACH_FILLER_DELAY` | `6.0` | Segundos entre frases de relleno habladas durante llamadas largas al LLM. |
| `MIRACH_FILLERS` | _(localizado)_ | Override de fillers separado por barras, p. ej. `"Espera.\|Pensando."`. |

## Servidor HTTP/SSE (widget + API móvil)

| Variable | Por defecto | Descripción |
|---|---|---|
| `MIRACH_SERVER_ENABLED` | `1` | Define `0` para desactivar el servidor HTTP por completo. |
| `MIRACH_SERVER_HOST` | `127.0.0.1` | Dirección de bind. Define `0.0.0.0` para permitir conexiones desde la app de Android. |
| `MIRACH_SERVER_PORT` | `7270` | Puerto TCP en el que escucha el servidor. |

## Búsqueda web

| Variable | Por defecto | Descripción |
|---|---|---|
| `MIRACH_SEARCH_REGION` | `wt-wt` | Código de región de DuckDuckGo (p. ej. `us-en`, `es-es`, `mx-es`). |

## Obsidian (memoria persistente)

| Variable | Por defecto | Descripción |
|---|---|---|
| `MIRACH_OBSIDIAN_VAULT` | `~/ObsidianVault` | Ruta a la raíz de tu bóveda de Obsidian. |
