# Cómo ver las conversaciones

## En el navegador (comando de voz)

Di una de estas frases:

- **Español**: "muéstrame la conversación", "ver conversación", "lee la conversación"
- **Inglés**: "show conversation", "view conversation", "read the conversation"

Mirach genera una página HTML estilizada con un diseño de chat de tema oscuro y la abre en tu navegador por defecto.

## Archivos Markdown en bruto

```bash
# Última conversación
cat ~/mirach/logs/conversations/latest.md

# Todas las conversaciones
ls ~/mirach/logs/conversations/

# Una conversación específica
cat ~/mirach/logs/conversations/conversation_2026-01-15_14-30-00.md
```

Cada sesión crea un nuevo archivo con marca de tiempo. `latest.md` es un symlink al más reciente.

## Logs del daemon en vivo

```bash
# Journal de systemd (tiempo real)
journalctl --user -u mirach -f

# Log de archivo rotativo
tail -f ~/mirach/logs/daemon.log
```

## Formato de conversación

Los archivos Markdown usan esta estructura:

```markdown
# Conversation 2026-01-15_14-30-00

## You said (14:30:05)

¿Qué clima hace hoy?

---

## Assistant (14:30:12)

Hace 22°C y está soleado en tu zona.

---
```

El visor HTML lo renderiza como un diseño de chat con los mensajes del usuario a la derecha y los del asistente a la izquierda.
