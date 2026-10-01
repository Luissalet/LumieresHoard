<p align="center"><img src="app-icon.png" width="128" alt="Icono de Lumière's Hoard"></p>

# Lumière's Hoard

Un editor de vídeo local que funciona en el navegador y en tu propio ordenador. Tiene timeline multipista, edita por texto sobre transcripciones con tiempos por palabra, hace solo el trabajo repetitivo (silencios, muletillas, reencuadre vertical, subtítulos, cortes al ritmo, montajes desde un guion) y convierte peticiones en lenguaje natural en planes de edición que revisas antes de que cambie nada. Los renders son codificaciones de ffmpeg exactas al fotograma que usan el codificador de NVIDIA cuando lo hay. Todo está también disponible para asistentes por MCP, así que a un agente se le puede decir «toma este vídeo, quita los silencios, hazlo vertical y ponle subtítulos».

[English](README.md)

![El editor](docs/editor.png)

## Qué hace

**Biblioteca y timeline**
- Importa archivos o carpetas enteras por ruta (no copia nada) y sube archivos arrastrándolos. Cada medio recibe en segundo plano un proxy de 540p con GOP corto para moverse con fluidez, una tira de miniaturas y la forma de onda.
- Pistas de vídeo, audio y texto; la primera de vídeo es la principal y las demás se dibujan encima (imagen en imagen, superposiciones).
- Dividir, recortar con o sin arrastre, mover, deslizar el contenido sin mover el clip, mover un corte entre dos clips, borrar cerrando el hueco, cerrar huecos, duplicar, copiar y pegar, imán al cabezal, a los bordes y a los marcadores, rango de entrada y salida, marcadores y capítulos.
- Por clip: velocidad (el audio conserva el tono), inversa, volumen, fundidos de imagen y de sonido, encaje (contener, cubrir, llenar, tamaño nativo o el cuadro entero sobre un fondo desenfocado), posición, escala, rotación, opacidad, recorte, keyframes de posición, escala, rotación, opacidad y volumen con suavizado, efectos (color, LUT, desenfoque, nitidez, reducción de ruido, croma, viñeta, estilos; ruido de audio, mejora de voz, filtros, compresor, tono, eco) y 20 transiciones.
- Rótulos con estilos y animaciones (fundido, pop, subida, máquina de escribir). Imagen congelada. Estabilización (vid.stab en dos pasadas sobre el tramo que usa el clip). Música que baja cuando se habla.
- Deshacer y rehacer cada cambio, y un historial al que se puede volver.

**Edición por texto**
- Transcripción local con tiempos por palabra (faster-whisper; large-v3-turbo en GPU, un modelo más pequeño en CPU). Doce minutos de habla tardan medio minuto en una GPU.
- Las palabras que se oyen en el timeline se ven como texto: seleccionarlas y borrarlas las corta del vídeo, o se puede conservar solo una selección. Las correcciones del texto pasan a los subtítulos.
- Quita muletillas («eh», «o sea», «um», «like»…) y palabras repetidas; quita o acelera los silencios con un umbral sacado del ruido de fondo.
- Montaje desde guion: la grabación de alguien leyendo un guion (o un teleprompter), con repeticiones, queda como una toma por sección en el orden del guion, con un marcador de capítulo por sección. Si la charla sigue el guion con libertad, el modelo local encuentra qué frases cuentan cada sección.

**Herramientas automáticas**
- Reencuadre a 9:16, 1:1 o 4:5 con una cámara que sigue al sujeto (caras si está OpenCV, si no movimiento y detalle; fija dentro de una escena cuando el sujeto no se mueve, suave y con velocidad limitada cuando se mueve), o el cuadro entero sobre un fondo desenfocado.
- Subtítulos quemados en el render en seis estilos (limpio, negrita, karaoke, pop palabra a palabra, con caja, mínimo) y exportación SRT / VTT / ASS.
- Detección de escenas por cambio de color, con cortes o marcadores en cada escena.
- Corte de un grupo de clips o de las escenas de un vídeo al ritmo de una canción (tempo y pulsos calculados en la app).
- Momentos destacados de un vídeo largo (momentos fuertes, picos, movimiento, cortes, exclamaciones de la transcripción) y cortos verticales a partir de ellos con un clic.
- Igualar el volumen entre clips; exportaciones normalizadas a -14 LUFS (u otro objetivo) en dos pasadas.

**Planes de edición en lenguaje natural**
- Escribe «recorta los primeros 5 segundos, quita los silencios, subtítulos estilo karaoke y hazlo vertical» y recibes una lista de pasos (operaciones del timeline, herramientas, exportaciones) con una frase cada uno; puedes desactivar pasos, editarlos y aplicarlos como un solo paso de deshacer.
- Escribe el plan el modelo local cuando lo hay (a través del backend de modelos compartido de la familia); sin él, un lector por reglas entiende las peticiones habituales en español e inglés.

**Exportación**
- MP4 H.264 o H.265, MOV ProRes 422 HQ, una versión ligera de 720p, una vista previa rápida de 540p desde los proxies, GIF, MP3 y WAV; un tramo del timeline o todo; un .srt junto al vídeo; un EDL CMX 3600 de la pista principal; corte sin pérdida (copia de flujo, cortes en fotogramas clave) para grabaciones largas que solo hay que recortar.
- El timeline se parte en trozos que se codifican en paralelo (cada trozo abre solo los clips que muestra, así que cientos de cortes nunca son cientos de decodificadores) y se unen sin recodificar; el sonido se mezcla en una pasada. Cada exportación se comprueba: duración, tamaño, que haya sonido, sonoridad, saturación.
- El fotograma que muestra el timeline en cualquier instante se puede renderizar tal cual lo dibujaría la exportación.

## Cómo se arranca

Necesita Python 3.11+, Node 22 (para compilar la interfaz) y ffmpeg 6 o posterior en el PATH (`winget install Gyan.FFmpeg` en Windows).

```bash
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt      # Windows (venv/bin/python en otros sistemas)
venv\Scripts\python -m pip install -r requirements-gpu.txt  # opcional: transcribir en una GPU NVIDIA sin el toolkit de CUDA
npm ci && npx vite build
venv\Scripts\python -m lumiere_hoard                         # http://127.0.0.1:5198
```

`python scripts/launch.py` la arranca y abre el navegador; `python scripts/dev.py` levanta la API con recarga y el servidor de desarrollo de Vite.

Ajustes (entorno): `LUMIERE_PORT` (5198), `LUMIERE_DATA_DIR`, `LUMIERE_FILE_ROOTS` (carpetas que puede leer y donde puede exportar, separadas por `;` en Windows), `LUMIERE_ENCODER` (`auto`, `nvenc`, `x264`), `LUMIERE_RENDER_WORKERS` (trozos a la vez, 3), `LUMIERE_WORKERS` (tareas de fondo a la vez, 2), `LUMIERE_FFMPEG` / `LUMIERE_FFPROBE`. En la app: modelo, dispositivo e idioma de la transcripción, decodificación por GPU, carpeta de exportación, transcripción automática de lo que se importa y el modelo para los planes.

## Asistentes (MCP)

`mcp_server.py` es un puente MCP por stdio con 32 herramientas. Nunca abre la base de datos: cada llamada va a la app en marcha con el token de `data/mcp-token`, y arranca la app si no responde nadie.

```json
{"command": "<repo>/venv/Scripts/python.exe", "args": ["<repo>/mcp_server.py"],
 "env": {"LUMIERE_URL": "http://127.0.0.1:5198", "LUMIERE_TOKEN_FILE": "<repo>/data/mcp-token"}}
```

Las herramientas cubren la biblioteca (`media_import`, `media_analyze`, `transcript_get`, `highlights_find`…), los proyectos y el timeline (`project_create`, `project_get`, `timeline_edit` con 31 operaciones, `timeline_history`), la edición inteligente (`edit_command`, `text_cut`, `timeline_transcript`), los planes (`plan_create`, `plan_apply`), la salida (`render_start`, `job_status`, `renders_list`, `frame_snapshot`, `subtitles_export`) y los ajustes. Si una operación o un campo no existe, la respuesta lista todas las operaciones con sus campos; `project_get` pone primero los rótulos y lee los timelines largos por pista o por tramo; `frame_snapshot` devuelve la imagen (una imagen MCP) y las capas que se dibujan en ese instante (rótulos, subtítulos, medios), para que un asistente compruebe su propio trabajo. `faustus-plugin.json` describe la app, cómo se arranca y el puente para los anfitriones que lo leen.

## Cómo está hecha

- `lumiere_hoard/timeline.py`: el documento del proyecto (lienzo, pistas, clips, marcadores, subtítulos; milisegundos enteros).
- `lumiere_hoard/ops.py`: el vocabulario de operaciones, que se aplican todas o ninguna sobre una copia del proyecto; lo comparten la interfaz, las herramientas MCP y los planes.
- `lumiere_hoard/render/`: el compilador (timeline → scripts de filtros por trozo, transiciones con `xfade`, rótulos y subtítulos en un solo archivo ASS, el grafo de sonido desde másteres FLAC), el ejecutor (trozos en paralelo, sonoridad, mezcla final, control de calidad, fotogramas, corte sin pérdida) y la tabla de efectos (lo que no está en ella se rechaza).
- `lumiere_hoard/analysis/`: sonido (envolvente, silencios, sonoridad, tempo y pulsos), imagen (escenas, movimiento, el seguimiento del foco y los caminos de cámara), voz (transcripción, muletillas) y alineación con un guion.
- `lumiere_hoard/commands.py`, `plan.py`: edición inteligente y planes; `jobs.py`: la cola de tareas de fondo (proxies, análisis, transcripción, renders) con progreso y cancelación.
- `client/`: interfaz en React: biblioteca, vista previa compuesta en el navegador a partir de los proxies, timeline, inspector, vista de texto, asistente y exportación.

Pruebas: `python -m pytest -q` (medios sintéticos hechos con ffmpeg; los renders se comprueban fotograma a fotograma).

## Límites

- La vista previa en directo es una aproximación que dibuja el navegador (transiciones y efectos simplificados); «Fotograma exacto» y la exportación de vista previa a 540p muestran el resultado real.
- La velocidad es constante por clip (para cambiarla se divide el clip); no hay curvas de velocidad, secuencias anidadas ni multicámara.
- No separa hablantes; el montaje desde guion por sentido depende del modelo local y es más lento que el que va palabra por palabra.
- El seguimiento de caras usa los detectores clásicos de OpenCV: bien para gente que mira a cámara, peor de perfil o muy pequeña en el cuadro.

## Licencia

MIT.
