# Hojas de fotogramas del montaje

En el editor de vídeo, pulsa **Hoja** en la barra superior. Elige Resumen o
Cortes, ajusta la cantidad de fotogramas y su ancho y genera la hoja. El diálogo
muestra los tiempos reales y la procedencia de las capas, permite descargar el
PNG y el recibo JSON y abre la página HTML portátil.

`project_contact_sheet(project, mode="overview", count=12, width=320,
times=None, show=true)` exporta una revisión visual del timeline compuesto.
`POST /api/projects/{project}/contact-sheet` recibe las mismas opciones sin
`project` ni `show` y devuelve enlaces. El agente usa la ruta auditada existente
`POST /api/agent/call`, nombre `project_contact_sheet`; el puente MCP stdio
descubre el esquema automáticamente. `show=false` devuelve solo texto y
`true` añade la imagen JPEG.

El modo `overview` elige 2–16 fotogramas uniformemente en la cuadrícula nativa
de salida y termina en el último válido. No busca comienzos de clips: una
muestra puede caer dentro de un clip. El recibo JSON incluye
`sampling_policy.strategy`, la cantidad solicitada y la seleccionada, y
`frames[].sampling.grid_indices`. Si un timeline corto hace coincidir varios
puntos de la cuadrícula solicitada con el mismo fotograma, ese fotograma guarda
todos sus índices originales. Por cada capa de clip incluye
`layers[].timeline_position` (`clip_start`, `clip_interior`, `clip_end` o
`clip_start_end`) y `clip_timing` con límites exactos del timeline, fotogramas
de salida y distancia a los bordes del clip. Así se distingue una muestra
uniforme de un corte. `boundaries` genera pares antes y en los comienzos de
clips de la pista de vídeo principal; `truncated=true` señala cortes omitidos
por el límite elegido. Si no hay comienzos posteriores a cero, el recibo indica
la estrategia `start_and_last_frame_fallback` y el motivo en `fallback_reason`.
Ningún modo cubre todos los cambios de capas/efectos, finales de huecos ni
escenas de origen. `times` admite 1–16 milisegundos enteros dentro del montaje,
ajusta las peticiones a fotogramas reales y registra duplicados y peticiones
que convergen en el mismo fotograma. El recibo diferencia tiempo solicitado,
tiempo real y número de fotograma; una petición válida que redondea al final usa
el último válido.

Cada celda tiene 128–640 píxeles de ancho y hasta 1280 de alto para relaciones
extremas. Se usa el renderizador final con originales, incluidos recortes,
velocidad/inversión, capas, títulos y subtítulos. No se sustituye por proxies.
El tiempo de origen refleja el mapeo del clip en el timeline, no el PTS del
decodificador. Las secuencias anidadas incluyen revisión y atribución interna.
La hoja no comprueba continuidad semántica, movimiento ni sonido.

Se generan hojas JPEG y PNG, muestras PNG separadas, HTML portátil con PNG
incrustado y recibo JSON en `data/renders/frames`, descargables mediante
`/api/frames/{name}`. Los enlaces son `url`, `png_url`, `frame_url`, `html_url`
y `receipt_url`. El recibo registra revisiones SHA-256 de proyectos, tiempos
racionales, capas/clips/orígenes visibles, hashes de fuentes/artefactos y
rectángulos/hashes RGB de cada celda. El hash del recibo se devuelve aparte.

Si cambia el proyecto o una secuencia durante la captura, o los bytes de una
fuente antes de publicar, se rechaza la hoja y se eliminan sus salidas sin
publicar. Se comprueban bytes además de tamaño y fecha. Los errores de fuente
o render identifican fotograma y tiempo; puede quedar la caché ordinaria de
fotogramas del renderizador. No se modifican originales, proyecto, historial
ni configuración de la aplicación en marcha.

Las pruebas reales comprueban tres cortes de cuatro clips recortados con audio
y título, igualdad de píxeles PNG por celda, colores JPEG y comparación con un
vídeo completo exportado y decodificado por ffmpeg en los fotogramas indicados.
Un contador visual comprueba velocidad 2, reproducción inversa y última muestra.
Las regeneraciones deterministas conservan hashes. También se prueban API,
esquema MCP, descargas, invariancia y rechazos de cambios/fallos de render.

[Drift ya documenta hojas de contacto](https://github.com/CutWire-Studios/Drift/blob/17ab04e27076b877fb48e4bc2774d25627d7e761/docs/MCP.md)
en el HEAD observado `17ab04e27076b877fb48e4bc2774d25627d7e761`: muestreo por
cambios, uniforme, escenas y tiempos explícitos, atribución y avisos del final.
Esta ampliación cubre una carencia de Lumiere; no demuestra ventaja sobre Drift
ni paridad completa. Muestreo por dHash/cambios y escenas de origen sigue
pendiente. No se copia código de Drift.
