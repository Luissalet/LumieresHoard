---
name: Lumiere — motores creativos incorporados
description: Extracción acotada del diseño existente de controles, composiciones guardadas y resultados de 446.
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
  neutral-dim: "#a59ba6"
typography:
  body:
    fontFamily: "'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', 'Liberation Sans', Arial, sans-serif"
    fontSize: "13px"
    lineHeight: 1.4
  label:
    fontSize: "13px"
  button:
    fontSize: "12.5px"
    fontWeight: 550
  engine-status:
    fontSize: "12px"
  heading:
    fontWeight: 650
    letterSpacing: "-0.01em"
  diagnostic:
    fontSize: "11px"
rounded:
  field: "5px"
  button: "6px"
spacing:
  section-gap: "16px"
  form-gap: "10px"
  label-gap: "5px"
  result-gap: "8px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-ink}"
    rounded: "{rounded.button}"
    padding: "0 12px"
    height: "30px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
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
  saved-selector:
    backgroundColor: "{colors.neutral-field}"
    textColor: "{colors.neutral-text}"
    rounded: "{rounded.field}"
    padding: "0 4px"
    height: "28px"
---

# Design System: Lumiere — motores creativos incorporados

## Overview

**Creative North Star: "Taller existente de Lumiere"**

Modo **Operate**: recuperar una composición, crear una cartela editable o una secuencia a partir de un vídeo, ver el resultado y descargar sus archivos. La superficie prolonga el editor oscuro y violeta existente, con formularios compactos y controles nativos. Esta frase es una descripción inferida de la implementación; no establece una identidad nueva ni una metáfora elegida por Luis.

Fuente congelada examinada: `f635beea5c3bf1c2864ebb45e6f7e869ea4c9d53` de la candidata `D:/LocalAI/candidates/lumiere-native446-referencias-20261013`. Fuentes primarias: `client/src/components/CompositionsSection.jsx`, `client/src/index.css`, `client/src/hoard-theme.css`, `client/src/components/html-motion.css` y `client/src/components/ui.jsx`. Contexto contiguo: `docs/HTML-MOTION-DESIGN.md` de 439; procedencia técnica: `native/PROVENANCE.md`. No hay PRODUCT.md formal ni un DESIGN.md global en esta candidata. Se documenta una extensión estrecha, por instrucción expresa de trabajo autónomo de Luis; no se ha realizado entrevista ni reemplazado la identidad del producto.

Los tokens de frontmatter describen esta extracción fechada. El CSS y los componentes siguen siendo la autoridad de implementación. Este archivo independiente y su sidecar no sustituyen ni mezclan silenciosamente documentos de diseño ajenos.

**Key Characteristics:**

- Composiciones guardadas identificadas por nombre, motor propio y fecha.
- Texto de cartela y duración junto a la acción de creación.
- Estado de los motores y catálogos de herramientas consultables.
- Resultado inmediatamente después de sus controles y antes de Animación HTML.
- Archivos editables, PNG y vídeo conservan funciones distintas.
- Filas que se envuelven y rutas largas que se parten dentro del panel.

Evidencia visual leída, sin nuevas capturas ni navegador: `D:/LocalAI/research-inbox/referencias-20261013/native-qa/screens/desktop-motion-final.png` (1440×900), `mobile-motion-final.png` y `mobile-selector-final.png` (390×844). Son vistas con desplazamiento del panel, no una certificación de toda la página. R2 declara UI y binarios iguales a R1; la corrección R2 afecta a concurrencia de metadata. El detector del propietario sobre la ruta correcta de CompositionsSection devuelve `[]` en `native-qa/design-findings.json`; esto no prueba accesibilidad, funcionamiento ni ausencia universal de defectos.

## Colors

### Primary

El violeta distingue acciones principales, foco y la identidad Lumiere. `primary-hover` aclara el estado de interacción; `primary-ink` aporta texto oscuro a las acciones rellenas. Se mantiene la paleta `html[data-hoard-app="lumiere"]`, sin colores tomados de capturas de otros productos.

### Neutral

El fondo oscuro ciruela (`neutral-bg`) sostiene la superficie; los campos usan el tono hundido (`neutral-field`). Panel, elevación y hover aportan separación tonal. Texto claro, texto auxiliar y texto tenue tienen funciones distintas. Los bordes marcan separación y contorno de controles; su variante hover muestra interacción.

El borde efectivo de campos y botones secundarios se deriva en CSS mediante `color-mix(in srgb, var(--hoard-border) 55%, var(--hoard-border-hover))`. No se inventa un hexadecimal alternativo para esa mezcla. El resultado usa un separador con el borde del panel.

## Typography

El cuerpo hereda la familia sans de Hoard. La marca general usa la familia serif compartida, pero la cabecera de Motores creativos es un `h2` que no toma el estilo serif de `.section-title h2`; no se le atribuye un tamaño explícito que su fuente no define.

Las etiquetas visibles heredan el cuerpo. Estado de motor y ayudas son compactos; los botones usan el peso documentado en frontmatter, con mayor peso para la acción principal. Las rutas de diagnóstico son elementos `code` de tamaño menor, con familia monospace del navegador salvo otra cascada externa. No se les atribuye JetBrains Mono por analogía con `.mono`, clase que no utilizan.

Los nombres y la fecha del selector son contenido del proyecto. La fecha se genera con `toLocaleString(lang, {dateStyle:"short", timeStyle:"short"})`; su longitud varía con idioma y datos. La captura móvil muestra la opción larga parcialmente visible dentro del control nativo, sin convertirla en una promesa de visibilidad completa de todo nombre posible.

## Layout

La sección es una cuadrícula de una columna reducible (`minmax(0, 1fr)`), con margen vertical (20px). Cabecera y estado de motores emplean filas flexibles con salto de línea. El selector ocupa el ancho disponible y precede a los estados y formularios.

El formulario crea columnas automáticas con mínimo (140px) y alinea sus controles al final. En escritorio, texto, duración y botón comparten fila; en la captura de 390px los dos campos caben juntos y el botón pasa a la fila siguiente. No hay un breakpoint exclusivo de esta sección: la adaptación deriva del ancho y `auto-fit`.

La acción de secuencia y su ayuda también se envuelven. El texto sobre conservación del original queda junto al proceso. El resultado separa controles de artefactos mediante borde superior y padding (14px), con intervalos de resultado en frontmatter. PNG ajustado con `object-fit: contain`, ancho máximo (100%) y alto máximo (260px); conserva su proporción sin recortarlo. Los enlaces y rutas siguen al PNG. Las rutas usan `overflow-wrap: anywhere`.

La biblioteca, cabecera del producto, timeline y panel HTML quedan fuera de esta extracción. La captura móvil del selector incluye una parte de biblioteca para aportar contexto, sin ampliar el alcance. El propietario comunica `innerWidth = documentWidth = 390` y selector (324px) en SUBMISSION-446-R2.md; aquí se cita esa prueba como recibida, no como medición propia.

## Elevation & Depth

La superficie de motores y resultados es plana. La separación procede de tono, bordes y espacio. No utiliza una tarjeta con sombra nueva. La sombra compartida `--hoard-shadow` existe para otras superficies del editor; no se extrae como regla de este bloque.

Los botones secundarios tienen borde y tono de hover; los campos son hundidos. El estado deshabilitado baja opacidad (0.45) y cambia cursor. No se añade elevación artificial a formularios o descargas.

## Shapes

Los botones y los campos mantienen los radios compactos documentados. El selector conserva la apariencia nativa (`appearance: auto`). La vista PNG se presenta como el artefacto producido, sin un marco decorativo añadido. Los controles usan contornos de un píxel; el foco global es un contorno violeta de dos píxeles con desplazamiento de un píxel, mientras `.field:focus` suprime el contorno y cambia el borde a violeta.

## Components

### Acciones de creación y exportación

Crear cartela es la acción principal. Requiere texto no vacío y motor Motion disponible; durante la operación se deshabilita y muestra el Spinner existente. El campo de texto tiene máximo (300 caracteres); la duración ofrece mínimo (0.5s), máximo (30s) y paso (0.5s). Son condiciones observadas de este formulario, no nuevos topes globales de autonomía.

Importar copia y exportar vídeo es una acción secundaria. Requiere medio seleccionado y motor Edit disponible. Cuando falta un vídeo, se muestra una indicación concreta para elegirlo en la biblioteca. La creación no elimina el original.

### Composición guardada

La etiqueta rodea el selector, manteniendo la asociación nativa. Aparece cuando la lista contiene composiciones. Elegir una recupera su resultado; la opción vacía lo limpia. Durante operaciones permanece deshabilitado. La consulta puede filtrar por proyecto vinculado.

El resultado es persistente en el producto; el estado React seleccionado no se persiste por sí solo. Después de recargar se consulta de nuevo la lista y el usuario puede recuperar una composición. No se afirma que el selector conserve automáticamente la última selección.

### Estado de motor y herramientas

Cada motor muestra nombre propio, versión y número esperado de herramientas, o Motor sin compilar. Los botones consultan los catálogos reales y abren un `details` con lista desplazable de altura máxima (250px). Conserva nombres técnicos de herramientas; es una vista de capacidades, no un asistente visual de edición completo.

La interfaz confirma Lumiere Motion (21 herramientas nativas) y Lumiere Edit (9). Las 64 herramientas MCP del producto son el total comunicado por el propietario; no equivalen a 64 botones, ni garantizan paridad universal con los proyectos de procedencia.

### Resultado y archivos

El PNG usa texto alternativo localizado. El proyecto editable y el vídeo son enlaces distintos. La acción Renderizar cartela animada a H.264 aparece para Motion cuando no hay vídeo o el vídeo pertenece a una versión anterior. Un aviso informa si el PNG o el vídeo corresponde a una fuente anterior; los artefactos siguen accesibles.

Copiar URL para media_receive copia la URL disponible y cambia a URL copiada temporalmente (1800ms). No importa por sí solo el resultado en la biblioteca. Los nombres `.lumotion` y `.lumedit` son formatos propios; una importación histórica conserva el original y crea otra copia, según PROVENANCE.

### Errores y actividad

Los fallos se muestran mediante un párrafo `role="alert"` con el texto localizado del motor y detalle recibido. La fuente no establece estilo específico para `.error` en los archivos examinados; no se documenta una caja roja inexistente. La actividad utiliza el Spinner compartido: diámetro (14px), borde (2px), giro lineal (0.8s), sin animación decorativa en el resultado.

La fuente localizada cubre español e inglés; el resumen del catálogo conserva texto técnico inglés. No se declara una revisión exhaustiva de traducciones, lector de pantalla, reducción de movimiento o contraste calculado.

## Do's and Don'ts

### Do:

- **Do** prolongar los tokens Hoard de Lumiere y sus controles existentes.
- **Do** mantener resultados del motor cerca de sus acciones y antes de la sección HTML contigua.
- **Do** preservar nombre, motor y fecha como ayudas para recuperar trabajo guardado.
- **Do** distinguir PNG, archivo editable y vídeo; informar cuando pertenecen a una fuente anterior.
- **Do** permitir salto de línea en filas, ayudas y rutas largas sin imponer anchos de escritorio.
- **Do** conservar los originales y las licencias históricas al evolucionar formatos propios.

### Don't:

- **Don't** convertir esta ficha de superficie en un rediseño global o una marca elegida por Luis.
- **Don't** presentar un motor externo o un adaptador renombrado como parte incorporada: la decisión 475 exige código propio integrado.
- **Don't** inferir funciones activas de todas las bibliotecas copiadas, modelos instalados o paridad completa a partir del catálogo.
- **Don't** atribuir acciones a copiar una URL que la acción no realiza.
- **Don't** llamar prueba en vivo a lectura de fuente, capturas recibidas o resultados de otro agente.

Sidecar asociado: `docs/design/native-creative.design.json`, schemaVersion 2. Sus muestras estáticas reproducen estructura y CSS de los controles examinados; no ejecutan API, renderizadores, portapapeles ni recuperación de proyectos. Los tokens primitivos viven en este frontmatter; el sidecar solo añade estados y contexto.
