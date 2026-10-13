---
name: Lumiere — revisión de varios momentos
description: Extracción acotada del storyboard HTML de la tarea 475, revisión 2.
colors:
  primary: "#de6fe8"
  primary-hover: "#e692ee"
  primary-ink: "#1a131b"
  neutral-bg: "#1c141c"
  neutral-field: "#161016"
  neutral-panel: "#241b25"
  neutral-hover: "#382b39"
  neutral-border: "#423543"
  neutral-border-hover: "#69576b"
  neutral-text: "#ebe1ec"
  neutral-muted: "#bdb4be"
typography:
  body:
    fontFamily: "'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', 'Liberation Sans', Arial, sans-serif"
    fontSize: "13px"
    lineHeight: 1.4
  heading:
    fontWeight: 650
    letterSpacing: "-0.01em"
  button:
    fontSize: "12.5px"
    fontWeight: 550
  source:
    fontFamily: "var(--mono, monospace)"
    fontSize: "12.5px"
    lineHeight: 1.5
rounded:
  field: "5px"
  button: "6px"
spacing:
  field-gap: "6px"
  action-gap: "12px"
  form-gap: "14px"
  figure-gap: "16px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-ink}"
    rounded: "{rounded.button}"
    padding: "0 12px"
    height: "30px"
  button-secondary:
    backgroundColor: "{colors.neutral-hover}"
    textColor: "{colors.neutral-text}"
    rounded: "{rounded.button}"
    padding: "0 12px"
    height: "30px"
  field:
    backgroundColor: "{colors.neutral-field}"
    textColor: "{colors.neutral-text}"
    rounded: "{rounded.field}"
    padding: "0 8px"
    height: "28px"
---

# Design System: Lumiere — revisión de varios momentos

## Overview

**Creative North Star: "Taller existente de Lumiere"**

Modo Operate: guardar una composición, indicar momentos, ver la hoja conjunta y descargar la hoja, su fuente revisada o los PNG originales. Es una ampliación del bloque Animación HTML del taller de Proyectos. Conserva la identidad oscura y violeta, controles compactos, revisión visible y resultados dentro del panel con desplazamiento.

Esta extracción describe el candidato congelado `6dcc92d4fed427c1bd57dd1909355a10db16310c`, submission_revision=2 de la tarea 475. No acredita integración o activación en la copia principal. No crea una marca nueva, no reemplaza DESIGN.md y no convierte una decisión local en una regla para toda la familia.

**Key Characteristics:**

- Etiqueta y ayuda visible para introducir momentos en segundos.
- Hoja conjunta con tiempos y revisión; originales descargables por separado.
- Fuente HTML realmente capturada, archivada y descargable.
- Diferencias de revisión o fuente informadas junto al resultado.
- Filas de acciones adaptadas por envoltura y composición visual sin recorte.

Autoridad de implementación: `client/src/components/HtmlMotionSection.jsx`, `html-motion.css`, `client/src/index.css`, `hoard-theme.css` y `docs/HTML_MOTION.md`, dentro de `D:/LocalAI/candidates/lumiere-storyboard-referencias-20261013`. La ficha anterior `docs/HTML-MOTION-DESIGN.md` aporta contexto histórico de 439; sus seis herramientas/62 totales y referencias a adaptadores pendientes no describen el alcance actual.

Evidencia visual examinada, entregada por el implementador: `D:/LocalAI/research-inbox/referencias-ampliacion-20261013/screens/storyboard-desktop-r2.png` (1440×900), `screens/storyboard-mobile-r2.png` (390×844) y `storyboard-mcp.png` (1024×640). Desktop/móvil muestran momentos 0, 0.5, 1 y 3; el PNG MCP muestra 0, 1, 2 y 3. Son dos solicitudes distintas, no capturas contradictorias de la misma hoja. La miniatura móvil sirve para comparar; los enlaces conservan acceso a originales a resolución completa.

Método de esta documentación: lectura de fuentes, packet R2, recibo MCP y capturas existentes; sin servidor, navegador, render, modelo ni pruebas nuevas. Las comprobaciones R2 (38 pruebas del área, captura/race/fuentes relativas, build y MCP nativo con imagen/archivos) proceden del implementador y su packet; esta ficha no las convierte en pruebas propias ni afirma certificación de teclado, lector de pantalla o contraste calculado.

El contexto del implementador se invocó desde `client` con un target repetido y registró `targetExists=false`; esa resolución no es prueba de ausencia del componente. Aquí se leyó el archivo real. No existe PRODUCT.md formal. Se documenta una ampliación del sistema existente, conforme a la dirección acotada elegida y al permiso expreso de Luis para decidir. No se vuelve a ejecutar contexto. El hallazgo del detector sobre Arial pertenece al ejemplo HTML editable preexistente, no a una nueva fuente de la interfaz.

El sidecar `.impeccable/design.json` usa schemaVersion=2, siete muestras de componentes y once colores extraídos. La muestra de hoja incrusta el PNG MCP original, verificado contra su SHA, sin modificarlo. Sus enlaces conservan las rutas del recibo de la instancia privada de QA; las muestras no ejecutan operaciones del producto. Los avisos de revisión/fuente muestran estados presentes en el JSX, sin afirmar que aparezcan en las capturas de éxito. Las rampas OKLCH de ocho pasos se sintetizan para la visualización del panel y no añaden tokens normativos a la aplicación. No se introducen breakpoints ni sombras inexistentes.

## Colors

### Primary

El acento violeta existente identifica Guardar composición, foco y selección. Revisar varios momentos reutiliza el botón secundario; revisar no se presenta como otro guardado principal.

### Neutral

Fondos oscuros con matiz violeta distinguen campos hundidos y controles elevados. El texto claro sirve para acciones y resultados, el texto atenuado para ayuda, pies y diferencias informativas. Los bordes de campos/botones usan la mezcla existente `color-mix(in srgb, var(--hoard-border) 55%, var(--hoard-border-hover))`.

**The Content Palette Rule.** Los colores de una composición renderizada pertenecen a su contenido; no se incorporan al tema del taller.

## Typography

La interfaz conserva la pila sans y el cuerpo compacto del frontmatter. Marca y cabecera mantienen el tema serif existente encabezado por Cinzel. La fuente editable usa el fallback real `var(--mono, monospace)`; la existencia de `--hoard-font-mono` no implica que el textarea lo use. La ayuda de sintaxis se lee como texto normal junto al campo.

Los enlaces de descarga localizan los números: 0.5 de la entrada se muestra como 0,5 s en castellano. La sintaxis de entrada usa punto decimal y comas como separador, explícitamente explicado; el separador decimal localizado de la salida no redefine la entrada.

## Layout

La ampliación aparece después de revisar un fotograma y antes del estado/exportación de vídeo. Momentos y su botón comparten una fila flexible (`flex-wrap: wrap`, `align-items: end`) con las separaciones del frontmatter. La ayuda va inmediatamente después. En móvil, el botón pasa a su propia línea; la ayuda se envuelve y los enlaces ocupan varias líneas.

La imagen de la hoja ocupa todo el ancho disponible, con `object-fit: contain` y altura máxima (560px), superior al fotograma individual existente (360px). Se conserva la proporción y el contenido completo. El pie informa revisión y cantidad de fotogramas; la fila siguiente reúne hoja, fuente revisada y enlaces por instante. No hay nuevo breakpoint en html-motion.css ni navegación nueva. La geometría existente mantiene `repeat(auto-fit, minmax(140px, 1fr))`. La hoja MCP de cuatro momentos es 2×2 dentro del PNG; no son cuatro tarjetas HTML independientes.

## Elevation & Depth

La ampliación no añade sombra, contenedor flotante ni otra colección de tarjetas. Mantiene la profundidad tonal del taller y sus campos hundidos. Hereda las transiciones de botones (0.12s para fondo y borde) y el spinner existente (0.8s, lineal), sin animaciones ornamentales añadidas para la hoja.

## Shapes

Campos y botones usan los redondeos del frontmatter. La figura es abierta y rectangular; la imagen no recibe recorte decorativo ni una máscara que altere sus fotogramas. Los números forman parte de los enlaces y del propio PNG.

## Components

### Buttons

Guardar conserva su tratamiento principal. Revisar varios momentos reutiliza el secundario y queda deshabilitado cuando hay operación ocupada, cambios de borrador pendientes o exportación activa (`busy || dirty || active`). Es estado de edición existente, no una aprobación nueva. El deshabilitado hereda opacidad (0.45); hover/foco conservan el acento y contorno del tema.

### Inputs / Fields

Momentos usa un label visible, campo de texto y placeholder `0, 0.5, 1`. La ayuda visible explica comas, punto decimal y cuatro momentos si se deja vacío. `aria-describedby="html-motion-moments-help"` asocia campo y ayuda. La implementación también reconoce espacios/punto y coma como separadores, pero la ayuda promueve una sintaxis única clara. Los errores de operación usan `role="alert"` existente. No se afirma una evaluación de lector de pantalla a partir de estos atributos.

### Signature: hoja de fotogramas

- Solicitud: composición guardada, revisión mostrada y tiempos indicados; vacío solicita cuatro momentos por defecto incluyendo principio y final.
- Resultado: una figura con PNG real, alt de hoja/revisión y pie de revisión/cantidad. Hoja e imágenes tienen identidades propias; descargar no vuelve a ejecutar el render.
- Acceso: Descargar hoja, Descargar fuente revisada cuando existe su URL y un enlace por PNG original con su tiempo localizado.
- Revisión anterior: si cambia la revisión guardada, la hoja existente sigue legible y aparece «Esta hoja corresponde a una versión anterior».
- Fuente distinta: `source_matches_revision === false` muestra «La fuente capturada difiere de la versión guardada. La hoja conserva el HTML que se ha renderizado». Es aviso informativo; no hay nueva puerta o rechazo de un archivo editado.
- Cambiar composición limpia la hoja; los resultados de otra composición no se muestran en la nueva selección. Los borradores y capacidades de vídeo/restauración existentes siguen disponibles.

**The Captured Source Rule.** `source_sha256` identifica los bytes HTML usados por el worker y archivados; `saved_source_sha256` identifica el registro de revisión guardada. Una diferencia legítima se informa con metadata fiel y se renderiza. La captura se toma una vez y el worker verifica esos bytes antes de servirlos en la URL original del documento; un cambio posterior del archivo no sustituye el HTML revisado. Los recursos externos o relativos no quedan congelados por ese hash.

La ampliación vive en UI, API y MCP propios: `html_motion_storyboard`, séptima herramienta HTML, 65 herramientas totales según el recibo R2. El mismo servicio produce los archivos y la imagen MCP. `show=false` omite la imagen de la respuesta, conserva metadata/enlaces. La hoja no califica narrativa, no sintetiza fotogramas ausentes, no captura audio y no invoca un CLI/MCP externo. El vídeo H.264 sin audio y su incorporación a biblioteca/timeline permanecen en el flujo existente.

## Do's and Don'ts

### Do:

- **Do** mantener segundos, sintaxis de entrada explícita y tiempos localizados en las descargas.
- **Do** conservar originales y fuente capturada junto a la hoja, con revisión visible.
- **Do** explicar diferencias de revisión/fuente sin añadir una aprobación o rechazo nuevo.
- **Do** conservar las acciones anteriores de fotograma, vídeo, restauración y biblioteca/timeline.

### Don't:

- **Don't** tratar los colores de la composición como tokens del taller.
- **Don't** atribuir una hoja al hash guardado cuando se renderizaron bytes HTML distintos.
- **Don't** afirmar que el hash HTML congela recursos externos o certifica determinismo/calidad narrativa.
- **Don't** confundir documentación del candidato y evidencia entregada con activación en Main o pruebas propias.
