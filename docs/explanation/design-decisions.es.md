# Decisiones de diseño

## STT y TTS locales, LLM en la nube

Mirach mantiene el reconocimiento de voz y la síntesis de voz locales (Whisper y Piper) pero delega el LLM a un backend en la nube o local vía OpenCode o un endpoint nativo compatible con OpenAI. Esto equilibra:

- **Privacidad**: las grabaciones de voz nunca salen de tu máquina. Solo el texto transcrito se envía al LLM.
- **Velocidad**: el STT y el TTS locales añaden ~0.5 s de latencia cada uno, independiente de las condiciones de red.
- **Flexibilidad**: puedes apuntar el backend nativo a una instancia local de Ollama para operación totalmente sin conexión.

## Daemon con modelos en RAM

Los modelos permanecen cargados de forma permanente. Cargar Whisper y Piper en cada invocación añadiría 3–7 segundos de latencia de arranque en frío por interacción — inaceptable para un asistente conversacional.

## Una sola tecla, tres estados

Una tecla para grabar, procesar e interrumpir. Esto coincide con cómo la gente realmente usa los asistentes de voz: quieres interrumpir una respuesta equivocada y decir de inmediato algo distinto, sin alcanzar una segunda tecla.

## Harness agéntico

En vez de llamar al LLM una vez y reproducir la respuesta, Mirach corre un bucle interno que maneja llamadas de herramientas, confirmaciones y compactación de contexto. El backend `opencode_serve` delega esto por completo al CLI `opencode` (que tiene su propio ecosistema de herramientas y gestión de sesiones). El backend `native` corre el bucle de forma nativa contra cualquier endpoint compatible con OpenAI.

Esta división significa que obtienes todo el ecosistema de skills de OpenCode por defecto, manteniendo la opción de correr localmente con Ollama para flujos sensibles a la privacidad.

## Motor de políticas antes de cada llamada de herramienta

El motor de políticas evalúa `policy.yaml` antes de que cualquier herramienta se ejecute. Esto da una capa de seguridad configurable: las reglas `deny` bloquean la ejecución de plano; otras reglas controlan mediante confirmación explícita del usuario. La app móvil y el widget web presentan las confirmaciones como notificaciones accionables — puedes aprobar o denegar desde tu teléfono mientras la PC está desatendida.

## Capa de visibilidad HTTP/SSE

Un servidor HTTP mínimo de la librería estándar publica los eventos de conversación como Server-Sent Events. Esto desacopla el pipeline de cualquier cliente: el widget de navegador, la app de Android y futuros clientes se suscriben todos al mismo flujo de eventos. El servidor no añade dependencias externas (sin FastAPI, sin framework asyncio).

## App de Android compañera

El teléfono es una segunda pantalla para un asistente de escritorio. Las restricciones de diseño:
- **Sin escucha permanente**: el teléfono no hace detección de actividad de voz ni de palabra de activación; tú inicias.
- **Sin enrutar audio al teléfono**: la PC habla por sus propios altavoces; el teléfono solo muestra la transcripción y te deja leer respuestas con el TTS del teléfono si lo prefieres.
- **Presencia en segundo plano vía servicio en primer plano**: cuando dejas la app, un servicio en primer plano abre su propia conexión SSE y muestra el estado actual en una notificación persistente, con botones de acción para aprobar/denegar.

## Whisper medium + int8

La configuración original usaba `large-v3-turbo` con `float16` (~2.3 GB de VRAM). El cambio a `medium` con `int8` (~700 MB de VRAM) intercambia 0.2 s de velocidad de transcripción por 1.6 GB de ahorro de VRAM — un buen trato ya que la llamada al LLM toma segundos de todos modos.

## Retroalimentación progresiva

Durante llamadas largas al LLM, una retroalimentación escalonada (frases de relleno habladas → notificaciones de escritorio → mensajes de "sigo trabajando") evita que los usuarios crean que el daemon se colgó. Las frases de relleno se pre-generan como archivos WAV para reproducción sin latencia.

## Bilingüe en escritorio + móvil

Los textos de escritorio y las frases de relleno viven en `i18n.py` bajo claves de idioma (`en`, `es`). Los textos móviles usan el pipeline ARB de `flutter gen-l10n`, que genera clases de búsqueda en Dart puro que funcionan sin un `BuildContext` — el isolate de segundo plano puede por tanto llamar `lookupAppLocalizations(Locale(code))` para localizar el texto de las notificaciones sin ningún canal de plataforma.

## Scripts de usuario sobre patrones fijos

Los comandos de voz personalizados viven en un directorio `user_scripts/` (gitignored) con comentarios de metadatos. Esto hace los triggers personales (no en el repo), extensibles (solo añade un archivo) y autodocumentados. El costo del LLM se evita por completo para frases que coinciden.

## Logs de conversación en Markdown

Las conversaciones se guardan como Markdown, no JSON ni una base de datos. Legibles para humanos, amigables con git y compatibles con cualquier herramienta de Markdown. El symlink `latest.md` da acceso rápido sin navegar archivos con marca de tiempo.

## Persistencia de sesión

El ID de sesión de OpenCode se guarda en disco para que las conversaciones sobrevivan a reinicios del daemon y del sistema. Un timeout de inactividad configurable asegura que las sesiones obsoletas finalmente expiren y se inyecte un contexto fresco.

## mirach.env para la configuración local

Todos los ajustes son variables de entorno. `run_daemon.sh` carga `mirach.env` (gitignored) antes de arrancar el daemon, dando un único lugar para configurar voz, idioma, host del servidor y claves de API sin tocar la unidad de systemd. La unidad de systemd carga las mismas variables vía líneas `Environment=`; un `EnvironmentFile` separado en un drop-in maneja los secretos (claves de API).
