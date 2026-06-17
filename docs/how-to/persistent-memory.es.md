# Cómo configurar la memoria persistente (Obsidian)

Mirach puede leer archivos de tu bóveda de Obsidian para restaurar contexto entre sesiones. Esto le da al LLM continuidad — recuerda tus preferencias, tareas pendientes y reglas.

## Archivos requeridos de la bóveda

Crea estos archivos en tu bóveda de Obsidian:

- **`conocimiento.md`** — Instrucciones y reglas persistentes que el asistente debe seguir siempre
- **`recordatorios.md`** — Tareas pendientes, recordatorios y cosas que dar seguimiento
- **`preferencias.md`** — Preferencias del usuario: idioma, tono, herramientas favoritas, hábitos

Estos archivos se leen al inicio de cada nueva sesión y se inyectan en el prompt del LLM como contexto.

## Configura la ruta de la bóveda

```bash
systemctl --user edit mirach
```

Añade:

```ini
[Service]
Environment=MIRACH_OBSIDIAN_VAULT=/home/tu/ObsidianVault
```

## Cómo funciona

1. Al inicio de cada nueva sesión del LLM (tras `SESSION_IDLE_TIMEOUT` de inactividad), Mirach lee estos archivos del disco a la RAM
2. Su contenido se formatea y se inyecta en el prompt de sistema antes de la primera consulta
3. La caché **no** se refresca en cada turno — solo en sesiones nuevas
4. Esto significa que puedes editar los archivos de la bóveda entre sesiones y los cambios se recogerán

## Timeout de sesión

El timeout de inactividad por defecto es 1 hora (`MIRACH_SESSION_IDLE_TIMEOUT=3600`). Tras 1 hora sin interacciones, la siguiente pulsación de tecla inicia una sesión fresca y recarga el contexto de Obsidian.

Para cambiarlo:

```ini
[Service]
Environment=MIRACH_SESSION_IDLE_TIMEOUT=1800
```

(30 minutos en este ejemplo)

## Persistencia de sesión entre reinicios

El ID de sesión de OpenCode se guarda en `~/.cache/mirach/session_id`. Esto significa:

- Si el daemon reinicia (restart de systemd, recuperación de fallo), la conversación continúa
- Si el sistema reinicia, la sesión sobrevive mientras no haya vencido el timeout
- Para forzar una sesión fresca: `rm ~/.cache/mirach/session_id && systemctl --user restart mirach`
