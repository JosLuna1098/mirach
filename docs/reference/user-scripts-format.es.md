# Referencia del formato de scripts de usuario

Los scripts de usuario son archivos de shell o Python colocados en `<mirach_dir>/user_scripts/` que el daemon parsea al inicio buscando frases de activación.

## Requisitos del archivo

- La extensión debe ser `.sh` o `.py`
- Debe ser ejecutable (`chmod +x`)
- Debe contener los comentarios de metadatos `# triggers:` y `# response:`
- Los metadatos deben aparecer antes de cualquier línea que no sea comentario o shebang

## Formato de los metadatos

```bash
#!/bin/bash
# triggers: frase uno, frase dos, frase tres
# response: Texto hablado tras la ejecución.
# description: Descripción legible (opcional).
```

### `# triggers:`

- **Requerido**
- Lista de frases de activación separadas por comas
- La coincidencia es **sin distinguir mayúsculas** y usa **coincidencia por subcadena**
- Ejemplo: `focus mode` coincide con "hey, ¿puedes activar focus mode por favor?"

### `# response:`

- **Requerido**
- Texto hablado por el TTS después de que el script corre
- Debe ser corto (1-5 palabras) para un flujo de conversación natural

### `# description:`

- **Opcional**
- Descripción legible para tu referencia
- El daemon no la usa de ninguna forma

## Ejecución

- Los scripts corren vía `subprocess.Popen` con `start_new_session=True`
- Corren en segundo plano — el daemon no espera a que terminen
- La respuesta se habla inmediatamente después de lanzar el script
- La salida estándar y de error no se capturan

## Reglas de parseo

1. El parser lee líneas desde el inicio del archivo
2. Las líneas que empiezan con `#!` (shebang) se omiten
3. Las líneas que empiezan con `#` se revisan buscando patrones de metadatos
4. La primera línea que no sea comentario ni shebang termina el bloque de metadatos
5. Si falta `triggers` o `response`, el script se omite con una advertencia

## Ejemplos

### Alternado simple

```bash
#!/bin/bash
# triggers: toggle nightlight, night light on, night light off
# response: Luz nocturna alternada.

pkill hyprsunset || (hyprsunset -t 3500 &)
```

### Con notificación

```bash
#!/bin/bash
# triggers: system status, system info, how is the system
# response: Revisando el estado del sistema.
# description: Muestra uso de CPU, memoria y disco en una notificación

CPU=$(top -bn1 | grep "Cpu(s)" | awk '{printf "%.0f", $2}')
MEM=$(free -h | awk '/Mem:/ {print $3 "/" $2}')
DISK=$(df -h / | awk 'NR==2 {print $3 "/" $2}')
notify-send "Estado del sistema" "CPU: ${CPU}%\nMemoria: ${MEM}\nDisco: ${DISK}"
```

### Script en Python

```python
#!/usr/bin/env python3
# triggers: what day is it, what's today, qué día es hoy
# response: Revisa la notificación.

import datetime
import subprocess
today = datetime.datetime.now().strftime("%A, %d de %B")
subprocess.run(["notify-send", "Hoy", today])
```
