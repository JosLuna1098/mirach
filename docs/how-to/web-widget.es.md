# Cómo usar el widget web

El widget web es una interfaz de navegador para el daemon en ejecución. Muestra la conversación en vivo, permite enviar turnos de texto, alternar el razonamiento, detener el turno actual y aprobar o denegar llamadas de herramientas — sin tocar la tecla.

## Abrir el widget

Con el daemon corriendo, abre esta URL en un navegador de la **misma máquina**:

```
http://127.0.0.1:7270
```

Eso es todo — no hay token que ingresar. El widget se sirve solo a loopback (`127.0.0.1`) y se autentica con un token interno inyectado en la página al servirla.

!!! note
    El widget es solo-loopback por diseño. Un navegador remoto recibe un `403`. Para manejar Mirach desde otro dispositivo, usa la [app de Android](../tutorial/mobile-app.md), que habla con la API JSON.

## Qué muestra

- **Transcripción en vivo** — tus turnos, la respuesta del asistente en streaming, llamadas y resultados de herramientas
- **Alternar razonamiento** (🧠) — muestra u oculta los bloques de razonamiento del modelo
- **Entrada de texto** — escribe un mensaje y envíalo, igual que hablar un turno
- **Botón de parar** — interrumpe el turno actual
- **Confirmar / Denegar** — cuando una herramienta necesita aprobación, aparecen botones en línea

El widget se suscribe al mismo flujo de eventos de `ConversationBus` que el pipeline de escritorio y la app móvil, así que todo se mantiene sincronizado: un turno iniciado por voz aparece en el widget, y un turno escrito en el widget lo habla la PC.

## Cambiar el puerto

El widget sigue `MIRACH_SERVER_PORT` (por defecto `7270`):

```bash
# mirach.env
MIRACH_SERVER_PORT=8080
```

Luego abre `http://127.0.0.1:8080`.

## Desactivar el servidor

Si no quieres el servidor HTTP (y por tanto el widget o la app):

```bash
# mirach.env
MIRACH_SERVER_ENABLED=0
```
