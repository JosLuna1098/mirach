# Referencia del protocolo IPC

El daemon se comunica con clientes externos vía un socket de dominio Unix.

## Ruta del socket

Por defecto: `/tmp/mirach.sock`

Cámbiala con la variable de entorno `MIRACH_SOCKET`.

## Protocolo

Basado en texto, un mensaje por conexión. El cliente se conecta, envía un mensaje y se desconecta.

### Mensajes

| Mensaje | Respuesta | Descripción |
|---|---|---|
| `toggle` | _(ninguna)_ | Dispara la transición de estado de la FSM (IDLE → RECORDING → PROCESSING → IDLE) |
| `ping` | `pong` | Chequeo de salud — responde de inmediato |

### Ejemplo: enviar un toggle

```python
import socket

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect("/tmp/mirach.sock")
s.sendall(b"toggle")
s.close()
```

### Ejemplo: chequeo de salud

```python
import socket

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(2)
s.connect("/tmp/mirach.sock")
s.sendall(b"ping")
response = s.recv(64).decode()  # "pong"
s.close()
```

## Manejo de errores

Si el socket no existe o la conexión es rechazada, el daemon no está corriendo. El script `trigger.py` maneja esto mostrando una notificación de escritorio.

## Seguridad

El socket se crea en `/tmp/` con permisos por defecto. En un sistema multiusuario, considera definir `MIRACH_SOCKET` a una ruta en un directorio privado.
