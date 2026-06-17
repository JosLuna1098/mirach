# Interfaces y casos de uso

Mirach tiene tres interfaces al mismo daemon. No son alternativas que eliges una vez: cubren situaciones distintas, y la mayoría de usuarios se mueve entre ellas durante un día normal.

| Interfaz | Entrada | Salida | Alcance | Mejor para |
|---|---|---|---|---|
| **Tecla** (`Alt+Z`) | Voz | Hablada | Frente al teclado | Preguntas rápidas con las manos en el teclado |
| **Widget web** | Texto | Hablada (PC) + en pantalla | Misma máquina, navegador | Leer respuestas largas, copiar la salida, ver herramientas ejecutarse |
| **App de Android** | Voz + texto | En pantalla + TTS opcional del teléfono | Cualquier dispositivo en la red | Lejos del escritorio, aprobar acciones en remoto |

Las tres comparten una conversación y una sesión. Un turno que inicias por voz aparece en el widget y en la app; un turno que escribes en el teléfono lo habla la PC. Nada queda aislado.

## ¿Por qué no solo la tecla?

La tecla es el camino más rápido cuando estás sentado frente a la máquina y la respuesta es corta. Se queda corta en tres situaciones comunes:

1. **La respuesta es larga o estructurada.** La salida hablada es lineal y desaparece en cuanto termina. Un comando, una lista, un bloque de código o una ruta son dolorosos de consumir de oído.
2. **No estás en el escritorio.** La tecla vive en la PC. Si estás al otro lado de la sala o en otra parte de la casa, no puedes pulsarla — y no puedes escuchar una pregunta de confirmación.
3. **Una herramienta necesita aprobación y no estás.** El motor de políticas se pausa en acciones sensibles y espera. Si no hay nadie para confirmar, el turno se queda atascado.

El widget resuelve (1). La app resuelve (2) y (3). A continuación, escenarios concretos.

## Casos de uso del widget web

### Leer y copiar la salida

Le pides a Mirach que resuma un log o genere un comando de shell. Escuchar un comando de 200 caracteres leído en voz alta es inútil — pero el widget lo muestra en pantalla, donde puedes leerlo con cuidado y copiarlo a tu terminal. La PC igual habla la respuesta, así que tienes ambos canales a la vez.

### Ver una tarea agéntica desplegarse

Cuando Mirach ejecuta herramientas (shell, ediciones de archivos, búsqueda web), el widget transmite cada `tool_call` y `tool_result` como una tarjeta. Ves exactamente qué ejecutó y qué devolvió, en vez de inferirlo de un resumen hablado. Esto hace que las confirmaciones del motor de políticas sean significativas: puedes leer el comando antes de aprobarlo.

### Seguir el razonamiento

Activa la vista de razonamiento (🧠) para observar el pensamiento del modelo en tareas más largas, y vuelve a ocultarla para respuestas limpias. Útil cuando depuras un prompt o verificas si el asistente entendió una petición complicada.

### Un canal silencioso

En una reunión o un espacio compartido, puedes escribir un turno en el widget en vez de hablar. La respuesta igual se habla en la PC — pero puedes silenciar los altavoces y leerla.

## Casos de uso de la app de Android

### Manejar la PC desde el otro lado de la sala

Estás en el sofá y quieres que la PC haga algo — iniciar una tarea, revisar un estado, ejecutar un script. La app envía el turno por la red; la PC lo ejecuta y lo habla. No hace falta caminar hasta el teclado.

### Aprobar acciones en remoto

Mirach trabaja en una tarea larga y llega a un paso que el motor de políticas controla — por ejemplo, borrar archivos o ejecutar un comando privilegiado. En vez de que el turno se atasque hasta que vuelvas al escritorio, la app levanta una notificación con botones **Aprobar** / **Denegar**. Decides desde tu teléfono, incluso con la app en segundo plano, y la tarea continúa.

### Voz desde el teléfono

La app hace reconocimiento de voz en el dispositivo, así que puedes hablar un turno al teléfono y que se transcriba y envíe sin estar en el micrófono de la PC. Con la "lectura de respuesta" activada, el teléfono también lee la respuesta — útil cuando los altavoces de la PC están apagados o estás fuera de alcance.

### Mantenerte informado en segundo plano

Cuando dejas la app, una notificación persistente mantiene viva la conexión y refleja el estado actual — inactivo, trabajando, esperando confirmación o error. Siempre sabes si Mirach está ocupado o atascado sin reabrir la app.

### Una segunda pantalla para una respuesta larga

La misma idea que el caso de leer-y-copiar del widget, pero en cualquier lugar: una respuesta larga o un comando generado llega como texto seleccionable en el teléfono, listo para leer o compartir.

## Elegir una interfaz

- **Pregunta corta, manos en el teclado** → tecla
- **Respuesta larga, código o un comando que copiarás** → widget (o app)
- **Ver herramientas ejecutarse / aprobar un comando sensible en el escritorio** → widget
- **Lejos del escritorio, o aprobar acciones en remoto** → app
- **Entorno silencioso** → widget o app (escribir en vez de hablar)
