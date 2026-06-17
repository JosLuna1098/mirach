# Cómo añadir un comando de voz personalizado (script de usuario)

Los scripts de usuario te permiten saltarte el LLM y ejecutar comandos de shell directamente cuando dices una frase de activación. Es instantáneo — sin retraso de transcripción más allá del STT inicial, sin llamada al LLM.

## Crea un script

Coloca un archivo `.sh` o `.py` en `<mirach_dir>/user_scripts/` con comentarios de metadatos al inicio:

```bash
#!/bin/bash
# triggers: focus mode, modo focus
# response: Modo de concentración activado.
# description: Activa el modo de concentración encendiendo la luz nocturna y No molestar

hyprsunset -t 3500 &
notify-send "Modo concentración" "Luz nocturna activada"
```

## Formato de los metadatos

| Comentario | Requerido | Descripción |
|---|---|---|
| `# triggers:` | Sí | Frases separadas por comas que activan este script (coinciden como subcadenas sin distinguir mayúsculas) |
| `# response:` | Sí | Texto hablado en voz alta después de que el script corre |
| `# description:` | No | Descripción legible (para tu referencia, no la usa el daemon) |

## Cómo funciona

1. El daemon parsea todos los scripts `.sh` y `.py` en `user_scripts/` al inicio
2. Cuando hablas, el texto transcrito se compara con todas las frases de activación (subcadena, sin distinguir mayúsculas)
3. Si hay coincidencia, el script corre en segundo plano vía `subprocess.Popen` y se habla la respuesta
4. No se hace ninguna llamada al LLM — esto evita todo el pipeline después de la transcripción

## Recarga los scripts

Tras añadir o editar scripts, reinicia el daemon:

```bash
systemctl --user restart mirach
```

## Scripts de ejemplo

### Alternar luz nocturna

```bash
#!/bin/bash
# triggers: nightlight, luz nocturna, night light
# response: Luz nocturna alternada.
# description: Alternar la luz nocturna de hyprsunset

pkill hyprsunset || (hyprsunset -t 3500 &)
```

### Info del sistema

```bash
#!/bin/bash
# triggers: system info, info del sistema, system status
# response: Aquí está el estado de tu sistema.
# description: Muestra uso de CPU, memoria y disco

CPU=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}')
MEM=$(free -h | awk '/Mem:/ {print $3 "/" $2}')
DISK=$(df -h / | awk 'NR==2 {print $3 "/" $2}')
notify-send "Info del sistema" "CPU: ${CPU}%\nMemoria: ${MEM}\nDisco: ${DISK}"
```

### Abrir una app

```bash
#!/bin/bash
# triggers: open browser, abrir navegador, launch firefox
# response: Abriendo el navegador.
# description: Lanzar Firefox

firefox &
```
