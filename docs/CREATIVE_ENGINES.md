# Local creative engines

Lumiere can create native motion graphics in EffectCraft and native editing
projects plus encoded videos in FilmCraft. The checked binaries are the
Windows x64 releases EffectCraft `v0.3.1` and FilmCraft `v0.2.1`; their live
headless MCP surfaces expose 21 and 17 tools respectively. Release claims are
limited to those pinned binaries. Lumiere does not claim feature parity with
either app.

## Local setup

The CLI bundles stay outside the Git repository. Lumiere discovers their
portable directories under `data/creative-apps/` or `data/craft-apps/`, from
`LUMIERE_CRAFT_BUNDLES`, or through this local-only file:

```json
{
  "effectcraft": "D:/Apps/effectcraft-cli.exe",
  "filmcraft": "D:/Apps/filmcraft-cli.exe"
}
```

The equivalent environment variables are `LUMIERE_EFFECTCRAFT_CLI` and
`LUMIERE_FILMCRAFT_CLI`. This machine's ignored `data/creative-engines.json`
points to the verified x64 bundles under `D:/LocalAI/native-craft-bundles/`.
The adapters start only each CLI's documented headless MCP mode. They do not
launch GUI windows.

Official release source and bundled documentation:

- [EffectCraft v0.3.1](https://github.com/storytold/effectcraft/tree/v0.3.1)
  (MIT OR Apache-2.0 code license).
- [FilmCraft v0.2.1](https://github.com/storytold/filmcraft/tree/v0.2.1)
  (MIT OR Apache-2.0 code license).

Source code licenses do not grant rights to footage, bundled fonts, models,
presets or other media assets; assess those separately before redistribution.

## Local routes and persistent artifacts

- `GET /api/creative/status` reports executable paths, pinned release labels,
  and expected live MCP tool counts.
- `GET /api/creative/tools/effectcraft` and
  `GET /api/creative/tools/filmcraft` start the headless CLI and return its
  complete current tools, descriptions and JSON schemas. FilmCraft exposes
  `command_list`, `command_run` and related commands inside its 17-tool MCP
  interface.
- `POST /api/creative/title-card` creates and saves a keyframed EffectCraft
  composition. Body: `{ "text", "width":1280, "height":720, "fps":24,
  "duration":3, "project_id":null }`.
- `POST /api/creative/{creative_id}/render-video` renders an existing
  EffectCraft project's active composition to H.264 MP4 with its native Rust
  encoder, then verifies codec, canvas, fps, duration and frame count with
  `ffprobe`. It returns the same editable project and preview links plus the
  MP4 and `media_receive_url`; `ffprobe` must be on `PATH` or configured with
  `LUMIERE_FFPROBE`.
- `POST /api/creative/film-sequence` copies a Lumiere library video into a
  project-specific folder, imports it into a FilmCraft sequence, saves the
  `.fcproj`, exports an H.264 MP4 and makes a PNG frame preview. Body:
  `{ "media_id", "project_id":null, "width":null, "height":null,
  "fps":null }`.
- `POST /api/creative/{creative_id}/call` opens the saved native project and
  invokes 1–32 native MCP calls in order. It returns the actual tool results
  and saves the project after the batch.
- `GET /api/creative/{creative_id}` reads the JSON manifest.
- `GET /api/creative/{creative_id}/preview`, `/project`, and `/render` serve
  the generated PNG, native `.ecproj`/`.fcproj`, and rendered video.

Every composition has a stable UUID `creative_id` and a folder under
`data/creative/projects/<id>/`. Native projects, source copies, previews,
video renders and a JSON manifest remain there. The manifest holds the optional
Lumiere `project_id` link and original `media_id`. Operations are recorded in
`data/creative/audit.jsonl`; each project has `engine-stderr.log` for its local
CLI diagnostics. The adapter confines path arguments and FilmCraft's imported
media paths to that project folder. FilmCraft always receives a copied source;
the library original remains unchanged.

The local executable map is `data/creative-engines.json` (ignored by Git); this
machine's map points to the verified Windows x64 bundles under
`D:/LocalAI/native-craft-bundles/`. Runtime state is isolated under
`data/creative/runtime/<engine>/`. MCP schemas are fetched live from each CLI
by the `/tools/<engine>` routes; they are not copied into a reduced static
catalogue. Each generic `/call` batch starts a fresh CLI process, opens the
saved native project, runs the supplied calls, saves, and exits. This preserves
the native tool names and arguments, but ephemeral selection and in-memory
undo history do not persist between batches. The title-card and film-sequence
workflows each keep one process open for their full sequence of calls.

## Real workflows

### EffectCraft title card

The title workflow calls `execute_command(comp.new)`, then
`execute_command(layer.newText)`, adds four native opacity keys with
`add_keyframe` on `transform/opacity`, saves with `save_project`, renders a
frame using `render_frame`, and reads the animated property through
`get_property`. The returned project remains editable; the PNG is the rendered
preview at 0.75 seconds (bounded by the supplied duration).

To create a video, call `render_title_video(creative_id)` or the REST route
above. It inspects the saved active composition with the pinned CLI's
`effectcraft-cli info --project <file> --json`, then invokes its documented
headless `render --project <file> --out <file> --format h264 --quality best`
command. The pinned release's own render queue and Rust encoder render the
complete project to disk; Python does not hold a frame sequence or require
FFmpeg to encode. The verified output is checked against the active project
settings before it becomes the manifest's current render.

EffectCraft's complete 21-tool surface is still available for broader work,
including `run_script`, `get_comp`, `get_layer`, `set_property`,
`add_keyframe`, `add_effect`, `list_effects`, `history`, `undo`, `redo` and
`render_frame`. Read the live schema before constructing calls.

### FilmCraft sequence export

The video workflow calls `media_import` on its isolated copy, then FilmCraft
commands `file.newSequence` with the imported item, `file.saveAs`, and
`file.exportMedia` using `format="h264"` and `wait=true`. It verifies the
sequence with `sequence_inspect` and renders a PNG monitor frame with
`render_frame`. The MP4 can be handed back to Lumiere through its existing
`media_receive` tool using the returned `media_receive_url`; if a Lumiere
`project_id` was supplied, pass it as `project` to add the received render to
that timeline.

FilmCraft's full 17 MCP tools are also available through `creative_tools` and
`creative_call`, including timeline command listing and execution, project and
sequence inspection, media import, preview rendering, and UI automation
tools. Generic calls open and save the same `.fcproj`.

## MCP integration for `agent_tools.py`

The REST routes above are already registered. Add the following agent-facing
models and wrappers alongside the existing `Tool(...)` definitions. These
wrappers call the same engine service without reimplementing its catalogue:

```python
class CreativeToolsArgs(BaseModel):
    engine: Literal["effectcraft", "filmcraft"]

class CreativeCallArgs(BaseModel):
    creative_id: str = Field(..., min_length=32, max_length=32)
    calls: list[dict[str, Any]] = Field(..., min_length=1, max_length=32)

class CreativeTitleArgs(BaseModel):
    text: str = Field(..., min_length=1, max_length=300)
    width: int = Field(1280, ge=16, le=8192)
    height: int = Field(720, ge=16, le=8192)
    fps: float = Field(24, ge=1, le=120)
    duration: float = Field(3, ge=0.5, le=30)
    project_id: Optional[str] = None

class CreativeFilmArgs(BaseModel):
    media_id: str = MediaId
    project_id: Optional[str] = None
    width: Optional[int] = Field(None, ge=16, le=8192)
    height: Optional[int] = Field(None, ge=16, le=8192)
    fps: Optional[float] = Field(None, ge=1, le=120)

class CreativeRenderArgs(BaseModel):
    creative_id: str = Field(..., min_length=32, max_length=32)

def run_creative_tools(svc: Services, a: CreativeToolsArgs):
    return CreativeEngines(svc.config.data_dir, port=svc.config.port).tools(a.engine)

def run_creative_call(svc: Services, a: CreativeCallArgs):
    return CreativeEngines(svc.config.data_dir, port=svc.config.port).call(a.creative_id, a.calls)

def run_creative_title(svc: Services, a: CreativeTitleArgs):
    if a.project_id:
        project_store.doc(svc, a.project_id)
    return CreativeEngines(svc.config.data_dir, port=svc.config.port).create_title_card(**a.model_dump())

def run_creative_film(svc: Services, a: CreativeFilmArgs):
    if a.project_id:
        project_store.doc(svc, a.project_id)
    media = media_store.get(svc, a.media_id)
    if media["kind"] != "video" or not media["has_video"]:
        raise LumiereError("FilmCraft needs a video source.")
    return CreativeEngines(svc.config.data_dir, port=svc.config.port).create_film_sequence(
        Path(media["path"]), source_media_id=a.media_id,
        width=a.width or media["width"], height=a.height or media["height"],
        fps=a.fps or media["fps"], project_id=a.project_id)

def run_creative_render_title_video(svc: Services, a: CreativeRenderArgs):
    return CreativeEngines(svc.config.data_dir, port=svc.config.port).render_title_video(a.creative_id)

# Add to lumiere_hoard.agent_tools imports:
# from .creative_engines import CreativeEngines
# from . import media as media_store, projects as project_store
# Then append to TOOLS:
Tool("creative_tools", "Get the full live MCP tool names, descriptions and JSON schemas from EffectCraft or FilmCraft. Herramientas nativas.\nKeywords: compositing, motion graphics, sequence, edición creativa.", CreativeToolsArgs, _ann(True), run_creative_tools),
Tool("creative_call", "Call 1–32 exact native MCP tools on an editable Lumiere creative project; returns the upstream responses. Ejecutar herramientas nativas.\nKeywords: effectcraft, filmcraft, keyframes, timeline, layers, effects.", CreativeCallArgs, _ann(False, True, False), run_creative_call),
Tool("creative_title_card", "Create a text title in EffectCraft with editable opacity keyframes and a rendered PNG preview. Cartela animada.\nKeywords: title, text animation, lower third, keyframes.", CreativeTitleArgs, _ann(False, True, False), run_creative_title),
Tool("creative_render_title_video", "Render a saved EffectCraft title composition to verified H.264 MP4 and return its media_receive URL. Render de cartela animada.", CreativeRenderArgs, _ann(False, True, False), run_creative_render_title_video),
Tool("creative_film_sequence", "Import a video copy into FilmCraft, create a sequence, save .fcproj and export H.264 MP4. Secuencia FilmCraft.\nKeywords: video sequence, encode, render, media_receive.", CreativeFilmArgs, _ann(False, True, False), run_creative_film),
```

`creative_title_card` and `creative_film_sequence` should call the REST workflows
or the same `CreativeEngines` methods. The API already links optional Lumiere
projects. The response's `media_receive_url` can be passed to Lumiere's
existing `media_receive`; no second editor or tool implementation is needed.
For the additional tool, define `CreativeRenderArgs` with a `creative_id: str`
field (32 lowercase hexadecimal characters), and a wrapper that calls
`CreativeEngines(svc.config.data_dir, port=svc.config.port).render_title_video(a.creative_id)`.

The Home UI section is in `client/src/components/CompositionsSection.jsx`.
Mount it with the currently selected media ID (or `null`) and active Lumiere
project ID (or `null`) when integrating the Home component.

## Verification and limits

Opt-in tests use only generated content, temporary project folders and the
configured native CLIs. They check a title layer's real keyframe property and
rendered pixels, the animated title's real H.264 output (metadata and different
start/middle frames), a FilmCraft project, actual encoded video streams, live
tool counts, generic project reopen/call/save, and original-byte preservation.
Run `pytest tests/test_creative_engines.py`; set `LUMIERE_CREATIVE_TEST_DATA`
to an isolated directory and `LUMIERE_CRAFT_BUNDLES` to the portable bundle
folder to enable the native executable tests.

This work exposes the editors' MCP features and implements these two workflows;
it does not reproduce either editor's full UI, undo semantics, format matrix,
effects inventory, rendering edge cases or compatibility guarantees. Those
remain unverified and are not parity claims.
