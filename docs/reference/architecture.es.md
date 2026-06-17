# Referencia de arquitectura

## Visión general del sistema

Mirach corre como un daemon en segundo plano en tu escritorio Linux y expone una API HTTP/SSE usada por el widget web y la app de Android. Una sola tecla dispara el pipeline de voz; el mismo pipeline puede manejarse en remoto desde la app móvil.

```
[Tecla] ──► trigger.py ──socket──► Assistant (FSM)
                                       │
                        ┌──────────────┼──────────────┐
                        ▼              ▼               ▼
                 AudioRecorder   WhisperTranscriber  PiperSpeaker
                  (sounddevice)   (faster-whisper)   (piper-tts)
                                       │
                                  LLMBackend (protocolo)
                                  ┌────┴────┐
                            opencode_serve  native
                            (opencode CLI) (Ollama/vLLM…)
                                       │
                                  ConversationBus ──► servidor HTTP/SSE
                                                           │
                                                  ┌────────┴────────┐
                                                Widget        App Android
                                              (navegador)    (flutter/mobile)
```

## Máquina de estados — `assistant.py`

`Assistant` posee una FSM de tres estados. `toggle()` es el único punto de entrada público, llamado por el servidor de socket Unix en cada mensaje `"toggle"`.

```
IDLE ──[toggle]──► RECORDING ──[toggle]──► PROCESSING ──[done]──► IDLE
                                                │
                                           [toggle]  interrumpe el pipeline
                                                │
                                             IDLE (reentra)
```

| Estado | Descripción |
|---|---|
| `IDLE` | Esperando una pulsación de tecla. Sin captura de audio. |
| `RECORDING` | El micrófono está abierto; los frames de audio se recogen en un buffer. |
| `PROCESSING` | Hilo en segundo plano ejecutando: `AudioRecorder.stop()` → `WhisperTranscriber.transcribe()` → `LLMBackend.query()` → `PiperSpeaker.speak()`. |

Un segundo `toggle()` durante PROCESSING interrumpe: `LLM.interrupt()` + `TTS.interrupt()` se llaman concurrentemente; el hilo del pipeline devuelve la FSM a IDLE.

## Backends del LLM — `mirach/harness/`

Dos backends implementan el protocolo `LLMBackend` (`llm_types.py`). Se selecciona con `MIRACH_BACKEND`.

**`opencode_serve` (por defecto)** — `mirach/harness/providers/opencode.py`

Lanza y supervisa `opencode serve`. Crea o reutiliza una sesión, traduce el flujo de eventos SSE (`message.part.delta`, `permission.updated`, `session.idle`) a eventos de `ConversationBus`, y aplica `PolicyEngine` en cada `permission.updated`. La sesión se reinicia tras `MIRACH_SESSION_IDLE_TIMEOUT` segundos de inactividad.

**`native`** — `mirach/harness/native_backend.py`

Corre un REPL interno completo de uso de herramientas contra cualquier endpoint compatible con OpenAI (Ollama, llama.cpp, vLLM…). Protocolo de invocación de herramientas: `auto | native | prompted`. La política se aplica antes de cada ejecución de herramienta. El historial vive en memoria; la sesión se reinicia tras el mismo timeout de inactividad.

## Motor de políticas — `mirach/harness/policy/`

`PolicyEngine` evalúa cada llamada de herramienta antes de ejecutarla contra `policy.yaml`. Las reglas son `allow` o `deny` con patrones glob sobre el nombre de la herramienta y los argumentos. Las reglas `deny` que coinciden bloquean la ejecución y emiten un evento `permission.updated` con `status: denied`. Las llamadas sin coincidencia que requieren confirmación disparan `status: awaiting_confirmation`.

## ConversationBus — `mirach/harness/events.py`

Un canal de publicación/suscripción en proceso. El backend activo publica eventos tipados (`queued`, `user_turn`, `text_delta`, `tool_call`, `tool_result`, `awaiting_confirmation`, `done`, `error`, `cost`). El servidor HTTP los reparte a los suscriptores SSE; el hilo de UI maneja el TTS desde el mismo bus.

## Servidor HTTP/SSE — `mirach/harness/server.py`

Un `ThreadingHTTPServer` de la librería estándar de Python que expone la API REST + SSE. Activado por defecto; se desactiva con `MIRACH_SERVER_ENABLED=0`.

Consulta la [Referencia de la API HTTP/SSE](http-api.md) para el contrato completo de endpoints.

## STT — `stt.py`

`WhisperTranscriber` captura a `MIRACH_SAMPLE_RATE` (por defecto 48 kHz), reduce a los 16 kHz requeridos por Whisper vía remuestreo polifásico (scipy) o un respaldo boxcar, y ejecuta la inferencia en GPU o CPU. Una pasada de calentamiento sobre un buffer en silencio corre al inicio para evitar latencia de arranque en frío.

## TTS — `tts.py`

`PiperSpeaker` sintetiza fragmentos que se transmiten directamente a un `sounddevice.OutputStream` — la reproducción empieza antes de que termine la síntesis. Un `_stream_lock` serializa las llamadas concurrentes a `speak()` (respuesta principal + bucle de relleno). Las frases de relleno cortas se pre-generan como archivos WAV al inicio (`prebake_fillers`) y se reproducen con `sd.play()`.

## i18n — `i18n.py`

El idioma de escritorio se elige al importar vía `MIRACH_LOCALE`. Añade un idioma extendiendo los diccionarios `STRINGS` y `FILLERS`. Los textos que no existen en el idioma actual recurren al inglés.

La app de Android usa un sistema separado basado en ARB (`mobile/lib/l10n/`) gestionado por `flutter gen-l10n`. El idioma de la app se persiste bajo la clave `mirach_lang` en `flutter_secure_storage`.

## ConversationLog — `conversation.py`

Cada sesión escribe un archivo Markdown bajo `logs/conversations/` y actualiza un symlink `latest.md`. Una nueva sesión empieza cuando vence el timeout de inactividad.

## Estructura del código fuente

```
mirach/
  __main__.py          — punto de entrada: `python -m mirach`
  assistant.py         — orquestador, FSM, hooks de apagado
  audio.py             — captura de micrófono thread-safe (sounddevice)
  stt.py               — WhisperTranscriber con calentamiento + reducción
  tts.py               — PiperSpeaker con streaming + fillers pre-generados
  llm_types.py         — protocolo LLMBackend + _strip_markdown()
  ipc.py               — servidor de socket Unix (toggle / ping)
  conversation.py      — logs Markdown + symlink latest.md
  conversation_html.py — visor HTML estilizado (tema oscuro, chat)
  obsidian_cache.py    — lector de la bóveda Obsidian en memoria (contexto de sesión)
  config.py            — todas las variables MIRACH_* con valores por defecto
  i18n.py              — textos del idioma de escritorio + frases de relleno
  langpack.py          — helper de idioma usado por i18n
  notify.py            — notificaciones de escritorio + generación de WAV de pitidos
  logging_setup.py     — logger de archivo rotativo + stdout para journalctl
  cli.py               — punto de entrada del CLI `mirach`
  harness/
    events.py          — ConversationBus + esquema de eventos tipados
    server.py          — servidor HTTP/SSE (API REST + widget)
    _widget.py         — HTML del widget web embebido
    loop.py            — REPL de herramientas del backend nativo (AgentLoop)
    native_backend.py  — NativeBackend: endpoint compatible con OpenAI
    context.py         — ContextManager (estrategia de compactación)
    build.py           — constructor del historial de conversación
    tool_protocol.py   — detección/normalización del formato de llamadas
    providers/
      base.py          — base abstracta de LLMBackend
      opencode.py      — OpenCodeServeBackend (opencode CLI)
      openai_compat.py — proveedor compatible con OpenAI directo
    policy/
      engine.py        — PolicyEngine: reglas allow/deny/confirm
      schema.py        — esquema de policy.yaml
    tools/
      registry.py      — registro de herramientas
      shell.py         — herramienta bash
      files.py         — herramientas de lectura/escritura de archivos
      web.py           — herramienta de búsqueda web
      memory.py        — herramienta de memoria Obsidian

trigger.py             — cliente de la tecla (envía "toggle" al socket)
run_daemon.sh          — configuración del path de librerías CUDA 12 + lanzador
pyproject.toml         — metadatos del paquete y dependencias
install.py             — asistente de instalación interactivo
bootstrap.sh           — instalador de una línea (deps del sistema → clone → asistente)
policy.yaml            — reglas de permisos de herramientas (gitignored; personal)
system_prompt.md       — prompt de sistema del LLM (gitignored; personal)
mirach.env             — overrides de config local (gitignored; personal)

mobile/                — app compañera de Android (Flutter)
voices/                — modelos de voz Piper (gitignored; descargados por el instalador)
logs/                  — logs del daemon + archivos Markdown de conversación
```

## Frecuencias de los pitidos

| Pitido | Frecuencia | Duración | Propósito |
|---|---|---|---|
| Iniciar grabación | 1320 Hz | 60 ms | Indica que el micrófono está abierto |
| Iniciar procesamiento | 660 Hz | 80 ms | Indica que la transcripción empezó |
| Apagado | 660 Hz → 330 Hz | 120 ms + 40 ms de pausa + 120 ms | El daemon se detiene |
