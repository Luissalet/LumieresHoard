# Revisar

Fallos, rarezas y cosas por comprobar. Cada entrada dice qué se vio y dónde.

## Abierto

- El montaje por sentido depende del modelo local en el 8081, que comparten otras sesiones: si está ocupado, la petición puede tardar o caducar (se devuelve un error claro y se puede repetir o usar el modo por palabras).
- Grabaciones de móvil con rotación: probado con -90; falta probar 180 y vídeos con rotación cambiante a mitad.
- Archivos de velocidad de fotogramas variable (grabaciones de pantalla): el proxy los normaliza, pero conviene revisar sincronía en grabaciones de más de una hora.

## Resuelto

- ffmpeg 7+ lista los filtros con dos columnas de banderas: la app creía que no había `ass` ni `vid.stab`.
- faster-whisper decodificaba con una versión de PyAV incompatible: ahora recibe las muestras ya extraídas.
- Faltaba `cublas64_12.dll` en Windows: `requirements-gpu.txt` + ruta de DLL; si la GPU falla, transcribe en CPU.
- El modelo con razonamiento se comía los tokens en respuestas estructuradas: van sin razonamiento.
- La alineación por sentido en JSON pasaba de 120 s: ahora pide líneas cortas «parte: rangos».
- 939 MB para 7:50 de vídeo vertical de móvil: techo de bitrate según resolución.
- Timelines de 150 clips lentos: menos lienzos, zoom agrupado por fotograma, montaje del preview limitado.
