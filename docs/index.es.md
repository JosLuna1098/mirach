# Documentación de Mirach

Asistente de voz local-first para Linux. Pulsa una tecla, habla y recibe la respuesta hablada — con memoria de conversación, uso de herramientas agéntico, un widget web y una app de Android.

## Inicio rápido

```bash
git clone https://github.com/JosLuna1098/mirach ~/mirach && python3 ~/mirach/install.py
```

## ¿Qué es Mirach?

Mirach corre como un daemon en segundo plano en tu escritorio Linux:

- **STT**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — Whisper `medium` en GPU, ~0.5 s
- **LLM**: un backend agéntico — [OpenCode CLI](https://opencode.ai) por defecto, o cualquier endpoint local compatible con OpenAI (Ollama, llama.cpp, vLLM)
- **TTS**: [Piper](https://github.com/rhasspy/piper) — TTS neuronal local, ~0.3 s
- **Control**: una sola tecla (por defecto `Alt+Z`) para grabar, procesar e interrumpir
- **Remoto**: un servidor HTTP/SSE que alimenta un widget de navegador y una app de Android

## Cómo funciona

1. Pulsa tu tecla → pitido agudo → empieza a hablar
2. Pulsa de nuevo → pitido grave → Mirach transcribe, ejecuta el LLM (con herramientas) y habla la respuesta
3. Pulsa durante el procesamiento → interrumpe de inmediato y empieza una nueva grabación

El LLM corre dentro de un bucle agéntico: puede llamar herramientas (shell, acceso a archivos, búsqueda web, memoria), y un motor de políticas decide qué llamadas se ejecutan automáticamente y cuáles necesitan tu confirmación. Las confirmaciones aparecen en el escritorio, el widget web y la app de Android.

## Capacidades

- **Sin escucha permanente** — el micrófono solo se abre con la tecla
- **Uso de herramientas agéntico** — shell, archivos, búsqueda web y memoria persistente, controlados por un motor de políticas
- **Persistencia de sesión** — las conversaciones sobreviven a reinicios del daemon
- **Retroalimentación progresiva** — frases de relleno y notificaciones durante llamadas largas al LLM
- **Scripts de usuario** — comandos de voz personalizados que evitan el LLM
- **Widget web** — sigue la conversación y confirma llamadas de herramientas en tu navegador
- **App de Android** — turnos por voz/texto, transcripción en vivo, confirmaciones remotas y presencia en segundo plano
- **Bilingüe** — inglés y español en la UI de escritorio y en la app de Android
- **Dos backends** — OpenCode CLI (por defecto) o un bucle nativo contra un modelo local

## Descargas

- **Código / instalador**: [github.com/JosLuna1098/mirach](https://github.com/JosLuna1098/mirach)
- **App de Android**: [último release](https://github.com/JosLuna1098/mirach/releases/latest) ([todos los releases](https://github.com/JosLuna1098/mirach/releases))

## Tres formas de usarlo

El mismo daemon y la misma conversación son accesibles de tres maneras — cubren situaciones distintas en lugar de reemplazarse:

| Interfaz | Cuándo conviene |
|---|---|
| **Tecla** (`Alt+Z`) | Preguntas rápidas con las manos en el teclado y respuesta hablada corta |
| **[Widget web](how-to/web-widget.md)** | Leer respuestas largas, copiar un comando, ver herramientas ejecutarse y aprobarlas |
| **[App de Android](tutorial/mobile-app.md)** | Manejar la PC desde el otro lado de la sala y aprobar acciones sensibles en remoto |

Un turno iniciado por voz aparece en el widget y en la app; un turno escrito en el teléfono lo habla la PC. Consulta [Interfaces y casos de uso](explanation/use-cases.md) para escenarios concretos.

## Estructura de la documentación

Esta documentación sigue el [framework Diátaxis](https://diataxis.fr/):

| Sección | Propósito |
|---|---|
| **[Tutorial](tutorial/get-started.md)** | Aprender haciendo — instala y ten tu primera conversación |
| **[Guías prácticas](how-to/user-scripts.md)** | Resolver problemas concretos — añadir scripts, cambiar voces, solucionar fallos |
| **[Referencia](reference/configuration.md)** | Detalles técnicos — configuración, arquitectura, la API HTTP/SSE |
| **[Explicación](explanation/design-decisions.md)** | Entender el porqué — decisiones de diseño y compromisos |

## Requisitos

- **Escritorio Linux** (Wayland o X11 con `notify-send`)
- **Python 3.11+**
- **GPU NVIDIA con CUDA 12** (el modo CPU funciona con más latencia)
- **Un micrófono**
- **Android 8.0+** (opcional, para la app)

## Siguientes pasos

- Sigue el [tutorial de Primeros pasos](tutorial/get-started.md) para instalar y configurar Mirach
- Configura la [app de Android](tutorial/mobile-app.md) para manejar Mirach desde tu teléfono
- Lee la [referencia de arquitectura](reference/architecture.md) para entender el diseño
- Revisa la [referencia de configuración](reference/configuration.md) para ajustar cada opción

## Inspiración

Este proyecto se inspiró en el video de Nate Gentile [Mi PC Linux ahora trabaja por mí (CachyOS + IA)](https://www.youtube.com/watch?v=b6uQTR7E9qg).
