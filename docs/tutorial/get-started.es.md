# Tutorial: Primeros pasos con Mirach

Este tutorial te guiará por la instalación de Mirach, la configuración de tu primer asistente de voz y tu primera conversación. Al final entenderás el flujo básico: pulsa una tecla, habla y recibe una respuesta hablada.

## Lo que aprenderás

- Cómo instalar Mirach en tu sistema
- Cómo configurar la personalidad de tu asistente
- Cómo usar la tecla para iniciar y detener la grabación
- Cómo se guardan y se ven las conversaciones

## Requisitos previos

- **Escritorio Linux** (probado en CachyOS + Hyprland; funciona cualquier escritorio Wayland/X11 con `notify-send`)
- **Python 3.11+**
- **GPU NVIDIA con drivers CUDA 12** (el modo CPU funciona pero añade 2-5 s de latencia)
- **Un micrófono**

## Paso 1: instala Mirach

Ejecuta el instalador desde tu terminal:

```bash
git clone https://github.com/JosLuna1098/mirach ~/mirach && python3 ~/mirach/install.py
```

El asistente interactivo te guiará por:

1. **Detección de GPU** — detecta CUDA automáticamente y fija el dispositivo correcto de Whisper
2. **Nombre del asistente** — cómo se llamará tu asistente (p. ej. "Mirach", "Aria", "Nexus")
3. **Idioma** — elige inglés o español para los textos de la UI y las frases de relleno
4. **Modelo Whisper** — `medium` (multilingüe) o `medium.en` (optimizado para inglés)
5. **Descarga de voz Piper** — selecciona y descarga un modelo de voz para la síntesis
6. **Ruta de la bóveda Obsidian** — opcional, para memoria persistente entre sesiones
7. **OpenCode CLI** — verifica o instala el backend del LLM
8. **Generación del prompt de sistema** — crea tu `system_prompt.md` personalizado
9. **Instalación de skills** — instala skills de OpenCode para capacidades extendidas
10. **Servicio systemd** — crea e inicia el servicio de usuario

Si quieres aceptar todos los valores por defecto sin interacción:

```bash
python3 ~/mirach/install.py --yes
```

### Después de instalar

Mirach usa el backend `opencode_serve` por defecto. Configura tu proveedor de LLM con:

```bash
opencode auth
```

Si prefieres una configuración totalmente local, cambia al backend `native` y apúntalo a un modelo local de Ollama — consulta la [referencia de configuración](../reference/configuration.md#backend-native).

### Configuración local con mirach.env

Los ajustes viven en `mirach.env` en la raíz del proyecto (cargado automáticamente por `run_daemon.sh`). El instalador lo crea por ti. Un archivo típico:

```bash
MIRACH_VOICE=daniela.onnx
MIRACH_LOCALE=es
MIRACH_WHISPER_LANG=es
MIRACH_SERVER_HOST=0.0.0.0
```

`MIRACH_SERVER_HOST=0.0.0.0` hace que el servidor HTTP sea accesible desde la [app de Android](mobile-app.md). Consulta la [referencia de configuración](../reference/configuration.md) para cada variable.

## Paso 2: entiende el flujo de la tecla

Mirach usa una sola tecla (por defecto: `Alt+Z`) para todas las interacciones. La tecla se vincula durante la instalación. Así funciona:

### Primera pulsación: iniciar grabación

1. Pulsa `Alt+Z`
2. Escuchas un **pitido agudo corto** (1320 Hz)
3. Aparece una notificación de escritorio: "🎤 Escuchando..."
4. Empieza a hablar — el micrófono ya está grabando

### Segunda pulsación: procesar y responder

1. Pulsa `Alt+Z` de nuevo cuando termines de hablar
2. Escuchas un **pitido grave corto** (660 Hz)
3. Mirach transcribe tu voz, consulta el LLM y habla la respuesta
4. Una notificación muestra lo que dijiste y la respuesta del asistente

### Tercera pulsación (durante el procesamiento o el habla): interrumpir

1. Pulsa `Alt+Z` mientras Mirach piensa o habla
2. La respuesta actual se **interrumpe de inmediato**
3. Escuchas el pitido agudo de nuevo — empieza una nueva grabación

Esto significa que la misma pulsación hace tres cosas distintas según el estado actual.

## Paso 3: ten tu primera conversación

Prueba a preguntar algo simple:

> "¿Qué clima hace hoy?"

O en inglés:

> "What time is it?"

Deberías escuchar:
1. El pitido grave cuando pulsas la tecla para terminar
2. Una notificación de procesamiento
3. Si el LLM tarda más de 10 segundos, aparece una notificación
4. Si tarda más de 30 segundos, escuchas "Sigo trabajando en ello..." (o el equivalente en inglés)
5. La respuesta hablada

## Paso 4: ve tu conversación

Tras tu primer intercambio, di una de estas frases:

- **Español**: "muéstrame la conversación", "ver conversación", "lee la conversación"
- **Inglés**: "show conversation", "view conversation", "read the conversation"

Mirach generará una página HTML estilizada y la abrirá en tu navegador. La página muestra tu conversación en un diseño tipo chat con tema oscuro.

También puedes encontrar el archivo Markdown en bruto en:

```
~/mirach/logs/conversations/latest.md
```

Cada sesión crea un nuevo archivo con marca de tiempo, y `latest.md` es un symlink al más reciente.

## Paso 5: personaliza tu asistente

La personalidad de tu asistente se define en `system_prompt.md`. Edítalo para cambiar cómo se comporta:

```bash
$EDITOR ~/mirach/system_prompt.md
```

Tras editar, reinicia el daemon:

```bash
systemctl --user restart mirach
```

El prompt de sistema controla:
- Idioma y tono
- Longitud de la respuesta (importante para el TTS — mantenla corta)
- Si confirma antes de acciones destructivas
- Cómo usar skills y herramientas

## ¿Qué sigue?

- Configura la [app compañera de Android](mobile-app.md) para manejar Mirach desde tu teléfono
- **Guías prácticas** para tareas concretas: añadir scripts de usuario, cambiar voces, solucionar fallos
- **Referencia** de todas las opciones de configuración, la arquitectura y la API HTTP/SSE
- **Explicación** de las decisiones de diseño detrás de Mirach

## Problemas comunes durante la instalación

**Notificación "El daemon no está corriendo" al pulsar la tecla**

Arranca el daemon:

```bash
systemctl --user start mirach
```

**Sin sonido del altavoz**

Verifica que tu voz Piper se descargó correctamente:

```bash
ls ~/mirach/voices/
```

Deberías ver al menos un archivo `.onnx`.

**Micrófono no detectado**

Lista los micrófonos disponibles:

```bash
~/mirach/venv/bin/python -c "import sounddevice as sd; print(sd.query_devices())"
```

Luego define `MIRACH_MIC` con una subcadena del nombre de tu micrófono en el archivo de servicio de systemd.
