# Referencia de la API HTTP/SSE

El daemon expone un servidor HTTP local (activado por defecto en el puerto 7270) que alimenta el widget de navegador y la app compañera de Android. Todos los endpoints excepto `/pair` requieren un token de dispositivo.

## Autenticación

Pasa el token de cualquiera de estas formas:

- Cadena de consulta: `?token=<token>`
- Cabecera: `Authorization: Bearer <token>`

Un token ausente o inválido devuelve `401 Unauthorized`.

## Emparejamiento

```
POST /pair
```

Intercambia un código de emparejamiento de un solo uso (impreso en los logs del daemon al inicio) por un token de dispositivo de larga duración. No requiere autenticación.

**Cuerpo de la petición:**
```json
{ "code": "XXXXXX", "device": "Mi teléfono" }
```

**Respuesta:**
```json
{ "token": "<token-de-larga-duración>" }
```

El código de emparejamiento rota tras cada uso exitoso. Reinicia el daemon o revisa los logs para un código nuevo.

## Flujo de eventos SSE

```
GET /events?token=<token>&since=<n>
```

Abre un flujo persistente de Server-Sent Events. Cada frame es:

```
data: <json>\n\n
```

Frames de heartbeat (keep-alive):

```
:\n\n
```

El parámetro `since` es el número de eventos ya recibidos. Al reconectar, pasa el conteo para reproducir los eventos perdidos.

### Tipos de evento

| Tipo | Descripción |
|---|---|
| `queued` | Un nuevo turno fue aceptado en la cola. `{ type, text, position }` |
| `queue_cleared` | La cola pendiente fue borrada. `{ type }` |
| `user_turn` | El LLM empezó a procesar un turno. `{ type, text }` |
| `text_delta` | Texto de respuesta incremental. `{ type, delta }` |
| `tool_call` | Se invocó una herramienta. `{ type, tool_call_id, name, arguments }` |
| `tool_result` | Una herramienta devolvió un resultado. `{ type, tool_call_id, content, is_error }` |
| `awaiting_confirmation` | Una herramienta espera que el usuario apruebe/deniegue. `{ type, tool_call_id, name, arguments }` |
| `done` | El turno está completo. `{ type, content }` — `content` es la respuesta final limpia. |
| `error` | Ocurrió un error. `{ type, message }` |
| `cost` | Uso de tokens del turno. `{ type, input_tokens, output_tokens }` |

## Entrada de turno

```
POST /turn
```

**Cuerpo de la petición:**
```json
{
  "text": "¿Qué clima hace hoy?",
  "interrupt": false,
  "clear_queue": false
}
```

- `interrupt: true` — interrumpe el turno en ejecución y opcionalmente la cola antes de procesar este.
- `clear_queue: true` — descarta todos los turnos en cola (no interrumpe el turno actual).

**Respuesta:**
```json
{ "status": "queued", "position": 1 }
```

## Detener

```
POST /stop
```

Detiene el turno actual y el TTS de inmediato. Equivalente a pulsar la tecla durante el procesamiento.

**Respuesta:** `{ "status": "ok" }`

## Confirmar / denegar llamada de herramienta

```
POST /confirm   { "tool_call_id": "<id>" }
POST /deny      { "tool_call_id": "<id>" }
```

Aprueba o rechaza una llamada de herramienta pendiente. El `tool_call_id` viene del evento `awaiting_confirmation`.

**Respuesta:** `{ "status": "ok" }`

## Cerrar sesión

```
POST /close_session
```

Fuerza una nueva sesión del LLM en el siguiente turno (limpia el historial).

**Respuesta:** `{ "status": "ok" }`

## Borrar cola

```
POST /clear_queue
```

Descarta todos los turnos en cola. El turno actual no se ve afectado.

**Respuesta:** `{ "status": "ok" }`

## Widget web

```
GET /
```

Devuelve el HTML del widget embebido. Solo accesible desde loopback (`127.0.0.1`); los clientes remotos (app móvil) usan la API JSON anterior.

## Bind para acceso remoto

Por defecto, el servidor hace bind a `127.0.0.1` (solo loopback). Para permitir que la app de Android se conecte por la red, define `MIRACH_SERVER_HOST=0.0.0.0` en `mirach.env`. El token de dispositivo es la única barrera de autenticación.

!!! warning
    Exponer el servidor en `0.0.0.0` otorga acceso por red a todas las herramientas que Mirach puede ejecutar. Usa Tailscale o un firewall para restringir el acceso a dispositivos de confianza.
