<p align="center"><img src="app-icon.png" width="128" alt="Lumiere's Hoard icon"></p>

# Lumiere's Hoard

A local video editor that runs in the browser and on your own machine. It has a multitrack timeline, edits by text on word-level transcripts, does the repetitive work automatically (silences, filler words, vertical reframing, captions, cuts on the beat, rough cuts from a script) and turns plain-language requests into edit plans you review before anything changes. Renders are frame-exact ffmpeg encodes that use the NVIDIA encoder when there is one. Everything is also exposed to assistants through MCP, so an agent can be told "take this video, cut the silences, make it vertical and caption it".

[Español](README.es.md)

![The editor](docs/editor.png)

## What it does

**Library and timeline**
- Import files or whole folders by path (nothing is copied); drag and drop uploads. Each media gets a 540p proxy with short GOPs for smooth scrubbing, a filmstrip and a waveform, made in the background.
- Tracks of video, audio and text; the first video track is the main one and the others draw on top (picture in picture, overlays).
- Split, trim with or without ripple, move, slip (change the content, keep the position), roll (move a cut between two clips), ripple delete, close gaps, duplicate, copy and paste, snapping to the playhead, edges and markers, in/out range, markers and chapters.
- Per clip: speed (with pitch-preserving audio) and speed curves (ease in and out, speed up, slow motion on a hit, or your own keys; the sound follows the curve), reverse, volume, video and audio fades, fit (contain, cover, fill, native size, or the whole frame over a blurred fill), position, scale, rotation, opacity, crop, keyframes for position, scale, rotation, opacity and volume with easing, shape masks (rectangle, rounded, ellipse; feather, invert, animated with keyframes), effects (colour, LUTs, blur, sharpen, denoise, chroma key, vignette, looks; audio denoise, voice enhance, filters, compressor, pitch, echo), 20 transitions.
- Titles with styles and animations (fade, pop, slide up, typewriter). Freeze frames. Stabilization (two-pass vid.stab on the span the clip uses). Music that ducks under speech.
- Nested sequences: another project used as one clip, nesting a selection into its own project and un-nesting it back; loops are refused and the nested render is cached until it changes.
- Multicam: recordings of the same event synced by their sound (offset and confidence per camera, manual correction), one continuous master sound, cut to an angle at the playhead by clicking its thumbnail, or cut automatically to whoever is speaking (minimum shot length, hysteresis).
- Templates: save a project as a template with named slots (intro, main, outro…) and make new projects by filling the slots with other media; titles, captions style, music and effects stay.
- Undo and redo for every change, plus a history you can jump back to.

**Text-based editing**
- Local transcription with word timestamps (faster-whisper; large-v3-turbo on the GPU, a smaller model on the CPU). Twelve minutes of speech take about half a minute on one GPU.
- The words heard on the timeline appear as text: select words and delete them to cut them from the video, or keep only a selection. Corrections to the text carry over to the captions.
- Speaker separation on the computer (a built-in engine from pitch and spectral shape, or voice embeddings when installed): rename speakers, fix who said what, keep or remove one speaker's parts, captions with each speaker's colour or name.
- Remove filler words ("eh", "o sea", "um", "like"…) and repeated words; remove or speed up silences with a threshold taken from the noise floor.
- Rough cut from a script: the recording of someone reading a script (or a teleprompter), retakes included, becomes one take per script section in script order, with a chapter marker per section. When the talk follows the script freely, the local model finds which sentences deliver each section.

**Automatic tools**
- Reframe to 9:16, 1:1 or 4:5 with a camera path that follows the subject (faces with OpenCV's YuNet detector, downloaded once, or the classic cascades, otherwise motion and detail; still inside a scene when the subject stays put, smooth and speed-limited when it moves), or keep the whole frame over a blurred fill.
- Captions burned into the render in six styles (clean, bold, karaoke, pop word by word, boxed, minimal), and SRT / VTT / ASS export.
- Scene detection by colour change, cuts or markers on each scene.
- Cut a set of clips or the scenes of a video on the beat of a song (tempo and beat tracking built in).
- Highlights of a long video (loud moments, peaks, motion, cuts, exclamations in the transcript; optionally the local model reads the transcript for hooks, punchlines and complete thoughts) and one-click vertical shorts from them.
- Background music: rank the tracks of a folder by how their tempo, length and energy fit the edit, and lay the chosen one under it trimmed, faded and ducked.
- B-roll suggestions: library clips whose words, names or tags match what is said in each sentence, placed muted over that range in one click.
- Loudness matching between clips; exports normalised to -14 LUFS (or another target) in two passes.

**Edit plans from plain language**
- Write "recorta los primeros 5 segundos, quita los silencios, subtítulos estilo karaoke y hazlo vertical" and get a list of steps (timeline operations, smart tools, exports) with a sentence for each; switch steps off, edit them, apply them as one undo step.
- The local model writes the plan when one is reachable (through the shared model backend of the family); a rule-based reader understands the common requests in Spanish and English when it is not.

**Export**
- MP4 H.264 or H.265, MOV ProRes 422 HQ, a light 720p version, a quick 540p preview from the proxies, GIF, MP3 and WAV; a range of the timeline or all of it; an .srt next to the video; several canvases at once (16:9, 9:16, 1:1, 4:5) in one job, each reframed on a copy of the project; subtitles translated by the local model with the original timing (SRT / VTT / ASS, burned in, or original and translation on two lines); a CMX 3600 EDL of the main track; a lossless cut (stream copy, cuts at keyframes) for long recordings that only need trimming.
- The timeline is cut into chunks encoded in parallel (each chunk opens only the clips it shows, so hundreds of cuts never mean hundreds of decoders) and joined without re-encoding; the sound is mixed in one pass. Every export is checked: duration, size, sound present, loudness, clipping.
- One timing rule for every frame (the last source frame reached before half an output frame later), tested frame by frame across chunk joins, frame rate changes and speed changes; the frame the timeline shows at any time can be rendered exactly as the export draws it.
- The live preview is drawn with WebGL2 from the proxies with the render's own maths (fit modes, blurred fill, keyframes, masks, speed curves, the 20 transitions, colour effects and LUTs), measured against the render at under 4 % mean difference (CSS preview when WebGL2 is missing).

## Running it

Needs Python 3.11+, Node 22 (to build the interface) and ffmpeg 6 or newer on the PATH (`winget install Gyan.FFmpeg` on Windows).

```bash
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt      # Windows (use venv/bin/python elsewhere)
venv\Scripts\python -m pip install -r requirements-gpu.txt  # optional: transcription on an NVIDIA GPU without the CUDA toolkit
venv\Scripts\python -m pip install -r requirements-speakers.txt  # optional: voice embeddings for similar voices
npm ci && npx vite build
venv\Scripts\python -m lumiere_hoard                         # http://127.0.0.1:5198
```

`python scripts/launch.py` starts it and opens the browser; `python scripts/dev.py` runs the API with reload and the Vite dev server.

Settings (environment): `LUMIERE_PORT` (5198), `LUMIERE_DATA_DIR`, `LUMIERE_FILE_ROOTS` (folders it may read and export to, separated by `;` on Windows), `LUMIERE_ENCODER` (`auto`, `nvenc`, `x264`), `LUMIERE_RENDER_WORKERS` (chunks encoded at once, 3), `LUMIERE_WORKERS` (background jobs at once, 2), `LUMIERE_FFMPEG` / `LUMIERE_FFPROBE`. In the app: speech model, device and language, GPU decoding, export folder, automatic transcription of new media, the model for plans, and who announces finished exports (`notify.via`: `auto`, `hub`, `off`).

## Assistants (MCP)

`mcp_server.py` is a stdio MCP bridge with 49 tools. It never opens the database: every call goes to the running app with the token in `data/mcp-token`, and it starts the app when nothing answers.

```json
{"command": "<repo>/venv/Scripts/python.exe", "args": ["<repo>/mcp_server.py"],
 "env": {"LUMIERE_URL": "http://127.0.0.1:5198", "LUMIERE_TOKEN_FILE": "<repo>/data/mcp-token"}}
```

The tools cover the library (`media_import`, `media_analyze`, `transcript_get`, `speakers_edit`, `highlights_find`, `music_pick`, `broll_suggest`…), multicam (`multicam_sync`, `multicam_create`, `multicam_switch`, `multicam_auto`), templates (`template_save`, `template_list`), projects and the timeline (`project_create`, `project_get`, `timeline_edit` with 40 operations, `timeline_nest`, `timeline_history`), smart edits (`edit_command`, `text_cut`, `timeline_transcript`), plans (`plan_create`, `plan_apply`), output (`render_start`, `job_status`, `renders_list`, `frame_snapshot`, `subtitles_export`, `subtitles_translate`) and settings. A wrong operation or field gets an answer listing every operation with its fields; `project_get` lists titles first and reads long timelines by track or time window; `frame_snapshot` returns the picture itself (an MCP image) and the layers drawn at that time (titles, captions, media), so an assistant can check its own work. Sibling apps can send media (`media_receive`, or the `lumiere.media.import` event at `/api/family/events`), bring a whole edit (`project_from_timeline`, below) and hear when renders and transcriptions finish (`GET /api/family/contract` lists the events). `faustus-plugin.json` describes the app, its launch and the bridge for hosts that read it.

## Family

- **Bring an edit from another app.** `project_from_timeline {title, fcpxml_path | edl_path | plan, fps?, media_dirs?}` makes a project from an FCP7 XML (`xmeml`) or a CMX 3600 EDL exactly as the video studio exports them (picture clips with their trims, a song on its own track, the sung lines as markers), or from a plan `{clips: [{path, in_s, out_s, track, start_s?}], markers: [{t, text}]}`. Everything lands as one undo step; media are read where they are (inside the allowed folders), the canvas comes from the XML (an EDL carries none: the shape of the first picture, `fps` or 24), and a clip whose file cannot be found is skipped and listed under `skipped` while the rest arrives. The answer is `{ok, project_id, url, clips, markers, skipped, duration_ms}`.
- **Renders as job events.** A render, a multi-format render or a lossless cut sends `lumiere.job.queued`, `.started`, `.progress` (at most one every 5 s, with `eta_s`) and `.cancelled`, and at the end `lumiere.render.done` / `lumiere.render.failed`, which the hub reads as `lumiere.job.done` / `.failed` with `kind: render`. Every event carries `job_id`, `title` (the project's name), `kind`, `progress` and `url`; a finished output also carries `ref` = `hoard://lumiere/render/<id>`, which the hub's rule hands to the publishing app to start a draft post. A render's failure is sent once; `lumiere.job.failed` stays for the jobs that are not renders.
- **Notifications through the hub.** When an export finishes or fails the hub is asked to tell you (normal priority, high on failure, a link to the project). Lumiere has no channel of its own: `notify.via` = `auto` (when the hub answers), `hub` (always ask) or `off` (nobody is told). A canceled render says nothing.

## How it is built

- `lumiere_hoard/timeline.py` — the project document (canvas, tracks, clips, markers, captions; integer milliseconds).
- `lumiere_hoard/ops.py` — the operation vocabulary, applied all or nothing to a copy of the project; the UI, the MCP tools and the plans share it.
- `lumiere_hoard/render/` — the compiler (timeline → per-chunk filter scripts, transitions with `xfade`, titles and captions as one ASS file, the sound graph from FLAC masters), the runner (parallel chunks, loudness, mux, quality check, frames, lossless cut) and the effect table (anything not in it is refused).
- `lumiere_hoard/analysis/` — sound (envelope, silences, loudness, tempo and beats), picture (scenes, motion, the focus track and camera paths), speech (transcription, filler words) and script alignment.
- `lumiere_hoard/commands.py`, `plan.py` — smart edits and plans; `jobs.py` — the background queue (proxies, analyses, transcription, renders) with progress and cancel.
- `lumiere_hoard/timeline_import.py` (FCP7 XML, EDL and plan readers and the project builder), `lumiere_hoard/jobevents.py` (render job events and hub notifications).
- `lumiere_hoard/speakers.py`, `multicam.py`, `music.py`, `broll.py`, `subtitles.py`, `family_events.py` — speaker separation, multicam groups, the music picker, b-roll suggestions, subtitle translation and the family events; `render/sequences.py` (cached nested renders) and `render/formats.py` (several canvases per job).
- `client/` — React interface: library, live preview drawn with WebGL2 from the proxies (`client/src/editor/gl/`), timeline, inspector, text view, assistant, export.

Tests: `python -m pytest -q` (synthetic media made with ffmpeg; renders are checked frame by frame). `python scripts/preview_check.py` (needs Playwright) measures the live preview against the render case by case.

## Limits

- The live preview matches the render closely but not bit for bit (the dissolve transition differs most); "Exact frame" and the 540p preview export show the real result. Denoise is not drawn in the preview.
- The meaning-based script assembly, model highlights and subtitle translation depend on the local model. The built-in speaker engine is tuned for clearly different voices; similar voices need the embeddings (requirements-speakers.txt) or the number of speakers.
- Face tracking needs one download of the YuNet model (230 KB); offline it falls back to the classic detectors, which are weaker in profile or small in the frame.

## Licence

MIT.


## OpenTimelineIO interchange

Use `project_export_otio` to save an actual `.otio` file, or download
`GET /api/projects/{id}/otio`. Import it with `project_from_timeline(otio_path=...)`.
The official OpenTimelineIO serializer carries every track, clip, gap, dissolve,
media reference and project marker. Titles, appearance, audio settings,
keyframes, speed ramps and project settings use versioned Lumiere metadata;
unchanged files preserve those editable values when reimported. External timing
or effect changes take precedence over previous clip metadata.

Each operation reports metadata-only, approximated, unsupported or omitted
items. FilmCraft sequence dimensions and sample rate are imported from its
metadata; unrecognized external namespaces, including proprietary effects and
framing, are reported rather than treated as preserved.
Animated/anisotropic FilmCraft framing is not mapped; static position, uniform
scale and rotation with a centered anchor and square pixels are mapped to an
editable native transform. Colors and other effects still require visual review.
Generic OTIO without
canvas metadata uses the native 1920×1080 canvas and reports that approximation.
Missing media leave gaps. Imported standard video tracks are silent; their sound comes
from OTIO audio tracks. Native embedded video sound round-trips as Lumiere
metadata, but is not expanded into an external audio track on export.
External fractional times are rounded to the
native millisecond clock with the maximum rounding error reported. Other
editors may not render Lumiere titles or appearance. Nested/trimmed compositions
and external reverse clips are not yet supported, and are rejected before a
project is created. This is not a claim of full editor interchange parity.

## Durable timeline edits over MCP

Pass an optional `request_id` to `timeline_edit` or `POST /api/projects/{id}/edit`.
Retry the same key with identical `ops`, `label` and `base_rev` after an interrupted
response to recover the original clip IDs and result without applying the edit twice.
The receipt survives restarts and is written atomically with the project/history.
A different edit needs a different key; reusing one for different content returns a
conflict. `rev` is the original result revision and `current_rev` reports the current
project revision. A retry after Undo returns the receipt without redoing the edit.
Calls without a key retain the normal behavior of applying each requested edit.


## Shared services (HoardLink 0.8.1)

The editor shares request guards, port discovery, tool argument/error handling and notification routing. Its styled ASS subtitles retain speaker colours and timing; image outputs opt out of text caps.

The vendored copy is maintained by HoardLink’s sync script. Windows validation and the family service contract are documented in HoardLink’s `docs/commons/windows-validation.md` and `docs/commons/services.md`.
