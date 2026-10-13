---
name: Lumiere — superficie de animación HTML
description: Notas extraídas de la ampliación HTMLmotion 439, sin sustituir la identidad existente.
colors:
  primary: "#de6fe8"
  primary-hover: "#e692ee"
  primary-ink: "#1a131b"
  neutral-bg: "#1c141c"
  neutral-field: "#161016"
  neutral-panel: "#241b25"
  neutral-elevated: "#2f2430"
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
  label-gap: "6px"
  settings-gap: "12px"
  form-gap: "14px"
  section-gap: "16px"
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

# Design System: Lumiere — superficie de animación HTML

## Overview

**Creative North Star: "Taller existente de Lumiere"**

Ficha acotada de una superficie construida: fuente → guardado → fotograma → vídeo → biblioteca o timeline. Conserva la identidad oscura y púrpura del taller, sus controles compactos y el desplazamiento interno. El nombre de arriba describe esa continuidad; no establece una nueva marca ni una composición global.

Fuente examinada: `5c3c2b12ce64861ea551af87b907f0d0562716d0` en `D:/LocalAI/candidates/lumiere-motion438-referencias-20261013`. Archivos: `client/src/components/HtmlMotionSection.jsx`, `html-motion.css`, `CompositionsSection.jsx`, `ui.jsx`, `client/src/index.css`, `hoard-theme.css` y `docs/HTML_MOTION.md`. Los tokens de frontmatter son una extracción fechada; la autoridad de implementación continúa en esos archivos. Documento independiente: no modifica el DESIGN.md ni la identidad del repositorio.

**Key Characteristics:**

- Etiquetas visibles y separación entre geometría, fuente y acciones del resultado.
- Fuente HTML editable; fotograma y vídeo ligados a revisiones guardadas.
- Controles nativos y filas de acciones que se envuelven al reducir el espacio.
- Resultados contenidos en el panel, con acceso por desplazamiento interno.

Evidencia visual observada: `D:/LocalAI/research-inbox/referencias-20261013/qa/screens/desktop-inputs-r2.png`, `mobile-inputs-r2.png`, `desktop-final.png`, `mobile-final.png`. Las entradas R2 muestran controles reales a 1440 y 390 px; los resultados muestran fuente, guardado, tiempo, fotograma y el comienzo del vídeo. Son vistas del panel con scroll, no capturas de documento completo. Las entradas vacías R1 no se usan.

Revisión independiente: `D:/LocalAI/research-inbox/referencias-review439-20261013/REVIEW-R2.md`, ship/approve de submission_revision=2; 16 pruebas del área y tres repros propios. Esta ficha no ejecutó pruebas nuevas, teclado real, contraste calculado, evaluación GLM ni captura en vivo. No se infieren esos resultados de imágenes.

## Colors

### Primary

Púrpura luminoso de Lumiere para el guardado principal, foco y selección. El estado hover usa el acento aclarado existente; texto oscuro sobre el botón principal. La ampliación reutiliza `--accent`, `--accent-strong` y `--accent-ink`, mapeados al tema compartido de Lumiere.

### Neutral

Fondos oscuros con matiz púrpura distinguen el lienzo de aplicación, campos hundidos y controles elevados. Texto claro para contenido; tono atenuado para instrucciones y pies. Los campos y botones reutilizan la mezcla de bordes existente: `color-mix(in srgb, var(--hoard-border) 55%, var(--hoard-border-hover))`.

**The Incumbent Theme Rule.** La superficie HTML utiliza los tokens existentes del taller. La paleta crema, tinta y terracota del ejemplo propio pertenece al contenido renderizado, no al tema de la aplicación.

## Typography

El cuerpo hereda la pila sans del tema y el tamaño compacto de la aplicación. Los encabezados de contenido conservan peso (650) y tracking (-0.01em). La marca de la cabecera mantiene la pila serif existente encabezada por Cinzel; HTMLmotion no la redefine.

La fuente editable usa `var(--mono, monospace)` con el interlineado extraído arriba. No se encontró declaración `--mono` en las dos hojas globales examinadas: no atribuir este textarea a JetBrains Mono solo porque el tema también define `--hoard-font-mono`.

El Arial del ejemplo portable aparece dentro del HTML de demostración. El warning del detector afecta ese contenido offline; no prueba un cambio de fuente del taller.

## Layout

La sección entra en `CompositionsSection` después de los controles existentes del taller. Un borde superior fino y separación inicial (18px) la delimitan. Selector guardado y nombre ocupan el ancho; geometría usa `repeat(auto-fit, minmax(140px, 1fr))`, con el gap de settings del frontmatter. No hay breakpoint nuevo en `html-motion.css`.

En la captura de 390px, los cuatro campos geométricos quedan en dos columnas; selector y nombre van de x≈28 a x≈352. Las acciones pasan a varias líneas. La fuente permite redimensionado vertical y envuelve cadenas largas (`pre-wrap`, `overflow-wrap: anywhere`), con ancho completo y `min-width: 0`. Los textos de ayuda se limitan a (75ch).

Fotograma y vídeo ocupan el ancho disponible, con `object-fit: contain` y altura máxima (360px). No se recorta la composición para llenar una tarjeta. La página utiliza scroll interno con cabecera visible; no se promete una vista completa simultánea de todos los controles o resultados.

## Elevation & Depth

HTMLmotion no añade sombras ni superficies flotantes: profundidad por fondos existentes, borde divisor y campos hundidos. El taller conserva sus sombras de otras superficies, pero no se convierten en una nueva regla para este bloque. Las transiciones de botones son las heredadas (0.12s para fondo y borde); el spinner existente gira (0.8s, lineal).

## Shapes

Botones suavemente redondeados y campos compactos usan las medidas del frontmatter. Los contenedores de esta sección permanecen abiertos, divididos por una línea, sin introducir una colección de tarjetas. El contenido del fotograma conserva su propia geometría y proporción.

## Components

### Buttons

Guardar composición conserva el botón principal existente y peso (650). Abrir archivo, cargar ejemplo, revisar fotograma, exportar, cancelar y restaurar usan el botón secundario. Hover y deshabilitado se heredan; el estado deshabilitado tiene opacidad (0.45). Foco visible del taller: contorno de acento (2px); el archivo añade `focus-within` con separación (3px).

### Inputs / Fields

Cada control está envuelto por un label con texto visible. Nombre y fuente son obligatorios; anchura/altura requieren valores positivos enteros y fps/duración positivos. El textarea conserva el borrador y su edición. Los campos de la sección restauran `focus-visible` explícito con separación (2px), por encima del reset global de foco del campo.

### Navigation

Se accede por el taller creativo de Proyectos, sin añadir una nueva ruta ni sustituir la navegación. La cabecera de las capturas es la heredada; no se redocumenta como una nueva identidad.

### Source, review and export

- Inicio: elegir composición o nueva; nombre, geometría, archivo/ejemplo y fuente; instrucción explícita de `window.seek(t)` en segundos; guardar.
- Guardado: revisión visible, aviso de cambios pendientes y acciones de tiempo, revisión PNG, exportación y descarga HTML. Revisar/exportar se deshabilitan con borrador sucio o trabajo activo; el borrador escrito durante un guardado sigue en el formulario.
- Fotograma: imagen con alt de acción, tiempo y revisión, más pie con esos datos. Es una revisión estática, no una calificación narrativa.
- Vídeo: estado de cola/progreso y cancelación del trabajo; controles nativos, descarga y recepción. El botón recibe la revisión mostrada y cambia de biblioteca a timeline si hay proyecto. Estado «Vídeo añadido» tras recibir.
- Restauración: selector de revisión y acción cuando hay más de una. Copia fuente y ajustes previos a una revisión nueva; no borra las posteriores.
- Errores usan `role="alert"`; revisión, trabajo, runtime y recepción usan `role="status"`. Son hechos de código, sin certificación de lector de pantalla.

La implementación HTMLmotion es propia, con Chromium/Playwright y FFmpeg/FFprobe como dependencias estándar. Seis herramientas `html_motion_*` añadidas, 62 herramientas totales según el recibo nativo revisado; la tabla REST/MCP de `HTML_MOTION.md` es el detalle funcional. El render produce MP4 H.264 sin audio: el sonido se añade en la timeline. Exige HTML completo con seek authored; no convierte automáticamente cualquier página o motor de animación.

Los controles de adaptadores externos anteriores visibles en las capturas están fuera de esta entrega. Su sustitución sigue en #446, conforme a decisión #475; HTMLmotion no los llama ni cierra esa deuda. La entrega no acredita paridad universal, audio, autonomía GLM o calidad narrativa.

## Do's and Don'ts

### Do:

- **Do** mantener tokens y controles existentes de Lumiere en esta superficie.
- **Do** conservar etiquetas visibles, revisión y tiempo al mostrar el resultado.
- **Do** permitir que filas, campos y fuente se adapten dentro del panel a 390px.
- **Do** separar los estilos del HTML authored de la identidad del taller.
- **Do** mantener fuente, geometría y salidas asociadas a su revisión guardada.

### Don't:

- **Don't** usar las entradas vacías R1 como prueba visual de controles.
- **Don't** afirmar teclado, contraste o accesibilidad completa a partir de capturas.
- **Don't** atribuir la fuente del ejemplo a la interfaz ni sintetizar una nueva marca.
- **Don't** presentar #439 como sustitución completada de los adaptadores de #446.
- **Don't** prometer audio o conversión automática de animaciones arbitrarias.

Sidecar de evidencia en `.impeccable/design.json`: solo metadatos y muestras CSS/HTML autónomas de componentes existentes. No instala un panel ni altera el producto. No se sintetizan ramps de color nuevos en esta extracción acotada.
