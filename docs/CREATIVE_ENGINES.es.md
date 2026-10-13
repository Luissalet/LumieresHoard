# Motores creativos incorporados

Lumiere incluye su código de composición y edición, proyectos, efectos y códecs
en `native/`. Son copias detached mantenidas como parte del producto, con licencias
y procedencia conservadas. No utiliza ejecutables ni servidores MCP de otra app.

Compila con Rust1.95.0 y `python native/build.py`. La interfaz Proyectos y las siete
herramientas creative_* utilizan estos motores propios. Identificadores: motion y
edit; formatos: .lumotion y .lumedit. Los catálogos tienen 21 y9acciones sin ventana
externa, que permiten descubrir y ejecutar los comandos del código incorporado.

Las cartelas conservan capas y keyframes; las secuencias usan copias de los medios y
exportan H264. El vídeo de composición se comprueba con ffprobe antes de anunciarlo
como exportado. La selección y el historial en memoria pertenecen a cada lote; el
contenido editable sí persiste. Los proyectos históricos se convierten a una copia
propia y se conserva su archivo original, sin obligación de compatibilidad futura.

La incorporación no demuestra por sí sola paridad con todas las acciones de una
ventana histórica ni descarga modelos de otras modalidades. API, comportamiento y
procedencia detallados en [CREATIVE_ENGINES.md](CREATIVE_ENGINES.md) y
[native/PROVENANCE.md](../native/PROVENANCE.md). La animación HTML tiene su flujo
propio, descrito en [HTML_MOTION.md](HTML_MOTION.md).

El catálogo de composiciones guardadas también abre sus archivos tras recargar, por UI y creative_list/creative_get. Las exportaciones capturan su fuente y SHA-256; conservan una edición concurrente y señalan cuándo el PNG o vídeo pertenecen a una fuente anterior. Lumiere ofrece64 herramientas MCP.
