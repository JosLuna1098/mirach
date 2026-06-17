# Tutorial: app de Android

La app de Android de Mirach es un control remoto para el daemon de la PC. Te permite enviar turnos por voz o texto, ver la transcripción completa de la conversación, aprobar o denegar llamadas de herramientas y seguir lo que Mirach hace — todo desde tu teléfono.

## Lo que necesitas

- Un teléfono Android (Android 8.0+, arm64 recomendado)
- El daemon de la PC corriendo con `MIRACH_SERVER_HOST=0.0.0.0` para que el teléfono pueda alcanzarlo
- Ambos dispositivos en la misma red (LAN o [Tailscale](https://tailscale.com))

## Paso 1: instala el APK

Descarga el último APK desde la [página de releases](https://github.com/JosLuna1098/mirach/releases/latest).

Elige `app-arm64-v8a-release.apk` para cualquier teléfono Android moderno (2018+). Instálalo:

1. Transfiere el APK a tu teléfono
2. Ábrelo — Android te pedirá permitir la instalación desde orígenes desconocidos
3. Acepta e instala

## Paso 2: arranca el daemon con acceso de red

En tu PC, arranca el daemon para que escuche en todas las interfaces:

```bash
./run_daemon.sh
```

Si `MIRACH_SERVER_HOST=0.0.0.0` está en tu `mirach.env` (el valor por defecto tras la instalación) el daemon es accesible por la red. Los logs mostrarán:

```
Pairing code: XXXXXX
```

Anota el código de emparejamiento — lo necesitas en el siguiente paso.

## Paso 3: empareja la app

1. Abre la app de Mirach en tu teléfono
2. Ingresa la IP y el puerto de tu PC: `192.168.x.x:7270`
   - Si usas Tailscale, ingresa la IP de Tailscale (`100.x.x.x:7270`)
3. Ingresa el código de emparejamiento de los logs del daemon
4. Toca **Conectar**

La app guarda el token y se reconecta automáticamente en aperturas futuras. El código rota tras cada emparejamiento exitoso.

## Funciones

### Entrada por voz (STT)

Toca el botón del micrófono para empezar a grabar. Toca de nuevo para enviar. Mantén pulsado para push-to-talk (mantén para grabar, suelta para enviar).

Con el envío automático activado, una cuenta regresiva de 3 segundos te da tiempo de editar la transcripción antes de que se envíe sola.

### Entrada por texto

Escribe directamente en el campo de entrada y toca **Enviar**.

### Control de turnos

- **Interrumpir** — interrumpe el turno actual y envía uno nuevo
- **Borrar cola** — descarta todos los turnos en cola; el turno actual continúa
- **Nueva conversación** — cierra la sesión y empieza de cero

### Transcripción de la conversación

La app muestra una transcripción en vivo: tus turnos, la respuesta del asistente, llamadas y resultados de herramientas, y solicitudes de confirmación. Los bloques de razonamiento (cuando están visibles) aparecen como secciones colapsables.

### Aprobar / denegar llamadas de herramientas

Cuando Mirach necesita ejecutar una herramienta que requiere confirmación, aparece una tarjeta en la transcripción con botones **Aprobar** y **Denegar**. También puedes denegar desde la notificación (cuando la app está en segundo plano).

### Presencia en segundo plano

Cuando dejas la app, una notificación persistente mantiene viva la conexión y muestra el estado actual de Mirach:

- **Toca para volver** — inactivo
- **Mirach está trabajando…** — procesando un turno
- **⚠ Confirmar: \<herramienta\>** — esperando tu aprobación (toca **Aprobar** / **Denegar** desde la notificación)
- **⚠ Mirach — error** — ocurrió un error

### Lectura de respuesta (TTS)

La app puede leer las respuestas de Mirach en voz alta usando el TTS nativo del teléfono. Tres modos:

| Modo | Comportamiento |
|---|---|
| Auto | Lee solo si el turno se envió por voz |
| Siempre | Lee todas las respuestas |
| Nunca | No lee |

### Idioma

La UI de la app y los textos de las notificaciones siguen el idioma fijado en el menú de opciones (inglés o español). El ajuste persiste entre reinicios.

## Menú de opciones

Toca ⋮ en la esquina superior derecha para abrir las opciones:

| Opción | Descripción |
|---|---|
| Envío automático de voz | Envía la transcripción automáticamente tras una cuenta regresiva |
| Mostrar razonamiento | Muestra los bloques de razonamiento en la transcripción |
| Mostrar llamadas a herramientas | Muestra las tarjetas de llamadas de herramientas |
| Mostrar resultados de herramientas | Muestra las tarjetas de resultados (colapsadas por defecto) |
| Lectura de respuesta | Modo TTS: Auto / Siempre / Nunca |
| Idioma | Idioma de la UI y las notificaciones (English / Español) |
| Desconectar de la PC | Olvida el token actual y vuelve a la pantalla de emparejamiento |

## Requisitos de red

La app se comunica directamente con el servidor HTTP de la PC. No se usa ningún relé en la nube.

- **Misma LAN**: ingresa la IP local de la PC (p. ej. `192.168.1.10:7270`)
- **Por Tailscale**: ingresa la IP de Tailscale de la PC (p. ej. `100.64.x.x:7270`)
- **El puerto 7270** debe ser accesible desde el teléfono hacia la PC
