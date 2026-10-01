# Revisar

Fallos, rarezas y cosas por comprobar. Cada entrada dice qué se vio y dónde.

## Abierto

Nada abierto. Los límites conocidos (vista previa aproximada, velocidad constante por clip, montaje por sentido que depende del modelo local) están en el README.

## Resuelto

- Prueba con Faustus (01-10): el 27B no sabía qué campos llevaba cada operación y probó a ciegas (`add_title`), llegó a dibujar el título con PIL e importarlo como imagen. Ahora hay alias (`add_title`, `remove_clip`, `duration`, `at`…) y los errores devuelven los campos de todas las operaciones.
- El asistente no podía abrir el fotograma (ruta fuera de sus carpetas) y confundió los subtítulos del proyecto con texto del vídeo original: `frame_snapshot` devuelve la imagen y la lista de capas visibles.
- `project_get` de un timeline de 125 clips pasaba de 26.000 caracteres y el asistente tenía que buscar el rótulo en el desbordamiento: ahora van primero los rótulos, con su estilo, y hay filtros por pista y tramo y un tope de clips por pista.
- Un nombre de archivo elegido para exportar acababa en «nombre.mp4-preview.mp4»: ahora se respeta tal cual.
- Los rótulos sin tamaño salían pequeños en vertical: el tamaño por defecto escala con el lienzo.
- Rotación de móvil: 90, 180 y 270 grados salen derechos en el render y en el proxy (`tests/test_sources.py`).
- Velocidad de fotogramas variable: destello y pitido juntos a menos de un fotograma en un clip corto (test) y al final de una grabación de una hora con fotogramas descartados (comprobado a mano: 38 ms, sin deriva).
- ffmpeg 7+ lista los filtros con dos columnas de banderas: la app creía que no había `ass` ni `vid.stab`.
- faster-whisper decodificaba con una versión de PyAV incompatible: ahora recibe las muestras ya extraídas.
- Faltaba `cublas64_12.dll` en Windows: `requirements-gpu.txt` + ruta de DLL; si la GPU falla, transcribe en CPU.
- El modelo con razonamiento se comía los tokens en respuestas estructuradas: van sin razonamiento.
- La alineación por sentido en JSON pasaba de 120 s: ahora pide líneas cortas «parte: rangos».
- 939 MB para 7:50 de vídeo vertical de móvil: techo de bitrate según resolución.
- Timelines de 150 clips lentos: menos lienzos, zoom agrupado por fotograma, montaje del preview limitado.
