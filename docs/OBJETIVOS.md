# Objetivos

Lo que falta para que el editor cubra todo lo que se le pide. Se tacha (o se borra) cuando está hecho y probado.

## Edición

- Curvas de velocidad dentro de un clip (rampas) en el compilador y en la interfaz; hoy la velocidad es constante por clip.
- Secuencias anidadas (un proyecto como clip de otro) para montajes con partes reutilizadas.
- Multicámara: sincronizar varias grabaciones por el sonido y cambiar de ángulo con un clic o por quién habla.
- Separación de hablantes en la transcripción (para cortar por persona en entrevistas y pódcasts).
- Máscaras de forma (rectángulo, elipse) con keyframes en clips superpuestos.
- Plantillas de proyecto con hueco para el medio («intro + charla + rótulo final») aplicables desde el asistente.

## Automático

- Seguimiento de caras con un detector moderno (YuNet de OpenCV o MediaPipe) cuando esté instalado; los Haar actuales fallan de perfil.
- Destacados con el modelo local leyendo la transcripción (qué momentos se entienden solos), además de las señales de audio y movimiento.
- Música de fondo: elegir de una carpeta la pista cuyo tempo y duración encajan con el montaje.
- B-roll sugerido: buscar en la biblioteca clips cuyas palabras de transcripción o escenas casan con lo que se dice.

## Salida

- Exportación de subtítulos traducidos (con el modelo local) además de los originales.
- Exportación directa de varios formatos a la vez (16:9 y 9:16 del mismo proyecto) en un solo trabajo.
- Vista previa en directo más fiel: transiciones y efectos de color calculados en WebGL.

## Familia

- Recibir medios desde otras apps de la familia (Prospero, Scribe) por `family.emit` y avisar al terminar un render.
