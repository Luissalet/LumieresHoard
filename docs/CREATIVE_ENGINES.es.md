# Motores creativos locales

Lumiere puede crear gráficos animados nativos con EffectCraft y proyectos de
edición nativos y vídeos codificados con FilmCraft. Los binarios comprobados
son las versiones Windows x64 EffectCraft `v0.3.1` y FilmCraft `v0.2.1`;
exponen en MCP sin interfaz 21 y 17 herramientas respectivamente. Las
capacidades aquí descritas corresponden a esos binarios. Esto no afirma paridad
con ninguna de las dos aplicaciones.

## Configuración local

Los paquetes CLI permanecen fuera del repositorio. Lumiere los descubre en
`data/creative-apps/` o `data/craft-apps/`, mediante `LUMIERE_CRAFT_BUNDLES`, o
con este archivo local:

```json
{
  "effectcraft": "D:/Apps/effectcraft-cli.exe",
  "filmcraft": "D:/Apps/filmcraft-cli.exe"
}
```

Las variables equivalentes son `LUMIERE_EFFECTCRAFT_CLI` y
`LUMIERE_FILMCRAFT_CLI`. El `data/creative-engines.json` ignorado de este PC
apunta a los paquetes x64 verificados en `D:/LocalAI/native-craft-bundles/`.
Los adaptadores inician el modo MCP sin interfaz documentado; no abren ventanas
gráficas.

Fuentes oficiales de estas versiones:

- [EffectCraft v0.3.1](https://github.com/storytold/effectcraft/tree/v0.3.1)
  (código MIT o Apache-2.0).
- [FilmCraft v0.2.1](https://github.com/storytold/filmcraft/tree/v0.2.1)
  (código MIT o Apache-2.0).

Las licencias del código no cubren los derechos de las grabaciones, fuentes,
modelos, presets ni otros recursos multimedia; deben revisarse por separado.

## Rutas y artefactos persistentes

- `GET /api/creative/status` muestra si se encontró cada ejecutable, su
  versión y el número esperado de herramientas MCP.
- `GET /api/creative/tools/effectcraft` y
  `GET /api/creative/tools/filmcraft` inician el CLI y devuelven su catálogo
  activo completo, descripciones y esquemas JSON. FilmCraft expone
  `command_list`, `command_run` y comandos relacionados dentro de sus 17
  herramientas MCP.
- `POST /api/creative/title-card` crea una composición EffectCraft con
  keyframes. JSON: `{ "text", "width":1280, "height":720, "fps":24,
  "duration":3, "project_id":null }`.
- `POST /api/creative/{creative_id}/render-video` renderiza la composición
  activa de un `.ecproj` a MP4 H.264 con el codificador Rust nativo de
  EffectCraft y verifica códec, dimensiones, fps, duración y número de frames
  mediante `ffprobe`. Devuelve enlaces al proyecto editable, al PNG, al MP4 y
  a `media_receive_url`. Requiere `ffprobe` en `PATH` o en `LUMIERE_FFPROBE`.
- `POST /api/creative/film-sequence` copia un vídeo de la biblioteca a una
  carpeta propia, lo importa en FilmCraft, crea una secuencia, guarda el
  `.fcproj`, exporta MP4 H.264 y produce una vista previa PNG. JSON:
  `{ "media_id", "project_id":null, "width":null, "height":null,
  "fps":null }`.
- `POST /api/creative/{creative_id}/call` abre el proyecto nativo guardado,
  ejecuta entre 1 y 32 llamadas MCP y guarda el proyecto al terminar.
- `GET /api/creative/{creative_id}` devuelve el manifiesto JSON.
- `GET /api/creative/{creative_id}/preview`, `/project` y `/render` sirven la
  imagen PNG, el proyecto `.ecproj`/`.fcproj` y el vídeo exportado.

Cada composición recibe un `creative_id` UUID estable y se guarda en
`data/creative/projects/<id>/`. Allí permanecen el proyecto nativo, las copias
de origen, la vista previa, el vídeo y el manifiesto JSON, que registra el
`project_id` de Lumiere opcional y el `media_id` de origen. El registro de
operaciones está en `data/creative/audit.jsonl`; cada carpeta de proyecto
incluye `engine-stderr.log`. Las rutas de archivos y los medios importados por
FilmCraft quedan confinados a su carpeta. FilmCraft recibe una copia; el medio
original de la biblioteca no se modifica.

El mapa local de ejecutables está en `data/creative-engines.json` y Git lo
ignora; en este equipo apunta a los bundles Windows x64 verificados de
`D:/LocalAI/native-craft-bundles/`. El estado del runtime queda separado en
`data/creative/runtime/<engine>/`. Las rutas `/tools/<engine>` consultan los
esquemas MCP activos del CLI y no los sustituyen por un catálogo reducido.
Cada lote genérico de `/call` inicia un proceso nuevo, abre el proyecto
guardado, ejecuta las llamadas, guarda y termina. Se mantienen nombres y
argumentos nativos, pero la selección temporal y el historial de deshacer en
memoria no sobreviven entre lotes. Los flujos de cartela y vídeo mantienen un
único proceso durante todas sus llamadas.

## Flujos reales

### Cartela con EffectCraft

El flujo llama a `execute_command(comp.new)`, después a
`execute_command(layer.newText)`, añade cuatro claves de opacidad con
`add_keyframe` sobre `transform/opacity`, guarda con `save_project`, genera una
imagen mediante `render_frame` y consulta la propiedad animada con
`get_property`. El `.ecproj` sigue siendo editable. La vista previa PNG
corresponde al segundo 0,75, limitado por la duración elegida.

Para obtener el vídeo, llama a `render_title_video(creative_id)` o a la ruta
REST anterior. Primero consulta el proyecto activo con el comando headless
`effectcraft-cli info --project <archivo> --json`; luego llama al comando
documentado `render --project <archivo> --out <archivo> --format h264` de la
release fijada. EffectCraft renderiza directamente al MP4 mediante su cola y
codificador nativos. Python no conserva una secuencia de imágenes en RAM o en
disco y no se necesita FFmpeg para codificar. Antes de publicar la ruta valida
el MP4 frente a las dimensiones, fps y duración del `.ecproj` guardado.

También se pueden usar las 21 herramientas MCP originales, como `run_script`,
`get_comp`, `get_layer`, `set_property`, `add_keyframe`, `add_effect`,
`list_effects`, `history`, `undo`, `redo` y `render_frame`. Consulta antes el
esquema activo.

### Vídeo con FilmCraft

El flujo importa la copia con `media_import`, crea la secuencia con el comando
FilmCraft `file.newSequence`, guarda mediante `file.saveAs` y exporta con
`file.exportMedia` usando `format="h264"` y `wait=true`. Verifica la secuencia
con `sequence_inspect` y genera la vista de monitor PNG mediante
`render_frame`. El MP4 puede volver a Lumiere con su herramienta existente
`media_receive`, pasando la URL devuelta en `media_receive_url`. Si se indicó
un `project_id`, pásalo además como `project` para añadir el render a esa línea
de tiempo.

Las 17 herramientas MCP de FilmCraft siguen disponibles por
`creative_tools` y `creative_call`, incluidas importación, inspección de
proyecto y secuencia, comandos de edición, previsualización y automatización de
la interfaz. Las llamadas genéricas abren y guardan el mismo `.fcproj`.

## Integración MCP en `agent_tools.py`

Las rutas REST ya están registradas. El documento inglés
[CREATIVE_ENGINES.md](CREATIVE_ENGINES.md) contiene los modelos Pydantic,
wrappers y cuatro entradas `Tool(...)` con los nombres `creative_tools`,
`creative_call`, `creative_title_card` y `creative_film_sequence`, listos para
añadir junto al catálogo MCP existente. Esas entradas usan las mismas
`CreativeEngines` y mantienen intacto el catálogo nativo de cada aplicación.

La interfaz Home está en `client/src/components/CompositionsSection.jsx`.
Al montarla, pásale el ID del medio seleccionado (o `null`) y el ID del
proyecto Lumiere activo (o `null`).

Para añadir el tool `creative_render_title_video`, define `CreativeRenderArgs`
con `creative_id: str` y un wrapper que llame a
`CreativeEngines(svc.config.data_dir, port=svc.config.port).render_title_video(a.creative_id)`.

## Verificación y límites

Las pruebas optativas usan contenido generado, carpetas temporales y los CLI
configurados. Comprueban keyframes y píxeles de la cartela, MP4 H.264 animado
con fps/duración y frames de inicio/medio distintos, proyecto y vídeo FilmCraft,
catálogos MCP activos, reapertura genérica de proyectos y preservación exacta
de los bytes originales. Para ejecutarlas, usa
`pytest tests/test_creative_engines.py`, define `LUMIERE_CREATIVE_TEST_DATA`
como carpeta aislada y `LUMIERE_CRAFT_BUNDLES` como carpeta de releases.

La integración expone las capacidades MCP y ofrece estos dos flujos; no
reproduce toda la interfaz, semántica de deshacer, matriz de formatos,
inventario de efectos, casos límite de render ni garantías de compatibilidad
de las aplicaciones originales. Esas áreas siguen sin verificarse.
