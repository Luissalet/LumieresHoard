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
- Per clip: speed (with pitch-preserving audio), reverse, volume, video and audio fades, fit (contain, cover, fill, native size, or the whole frame over a blurred fill), position, scale, rotation, opacity, crop, keyframes for position, scale, rotation, opacity and volume with easing, effects (colour, LUTs, blur, sharpen, denoise, chroma key, vignette, looks; audio denoise, voice enhance, filters, compressor, pitch, echo), 20 transitions.
- Titles with styles and animations (fade, pop, slide up, typewriter). Freeze frames. Stabilization (two-pass vid.stab on the span the clip uses). Music that ducks under speech.
- Undo and redo for every change, plus a history you can jump back to.

**Text-based editing**
- Local transcription with word timestamps (faster-whisper; large-v3-turbo on the GPU, a smaller model on the CPU). Twelve minutes of speech take about half a minute on one GPU.
- The words heard on the timeline appear as text: select words and delete them to cut them from the video, or keep only a selection. Corrections to the text carry over to the captions.
- Remove filler words ("eh", "o sea", "um", "like"…) and repeated words; remove or speed up silences with a threshold taken from the noise floor.
- Rough cut from a script: the recording of someone reading a script (or a teleprompter), retakes included, becomes one take per script section in script order, with a chapter marker per section. When the talk follows the script freely, the local model finds which sentences deliver each section.

**Automatic tools**
- Reframe to 9:16, 1:1 or 4:5 with a camera path that follows the subject (faces when OpenCV is installed, otherwise motion and detail; still inside a scene when the subject stays put, smooth and speed-limited when it moves), or keep the whole frame over a blurred fill.
- Captions burned into the render in six styles (clean, bold, karaoke, pop word by word, boxed, minimal), and SRT / VTT / ASS export.
- Scene detection by colour change, cuts or markers on each scene.
- Cut a set of clips or the scenes of a video on the beat of a song (tempo and beat tracking built in).
- Highlights of a long video (loud moments, peaks, motion, cuts, exclamations in the transcript) and one-click vertical shorts from them.
- Loudness matching between clips; exports normalised to -14 LUFS (or another target) in two passes.

**Edit plans from plain language**
- Write "recorta los primeros 5 segundos, quita los silencios, subtítulos estilo karaoke y hazlo vertical" and get a list of steps (timeline operations, smart tools, exports) with a sentence for each; switch steps off, edit them, apply them as one undo step.
- The local model writes the plan when one is reachable (through the shared model backend of the family); a rule-based reader understands the common requests in Spanish and English when it is not.

**Export**
- MP4 H.264 or H.265, MOV ProRes 422 HQ, a light 720p version, a quick 540p preview from the proxies, GIF, MP3 and WAV; a range of the timeline or all of it; an .srt next to the video; a CMX 3600 EDL of the main track; a lossless cut (stream copy, cuts at keyframes) for long recordings that only need trimming.
- The timeline is cut into chunks encoded in parallel (each chunk opens only the clips it shows, so hundreds of cuts never mean hundreds of decoders) and joined without re-encoding; the sound is mixed in one pass. Every export is checked: duration, size, sound present, loudness, clipping.
- The frame the timeline shows at any time can be rendered exactly as the export would draw it.

## Running it

Needs Python 3.11+, Node 22 (to build the interface) and ffmpeg 6 or newer on the PATH (`winget install Gyan.FFmpeg` on Windows).

```bash
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt      # Windows (use venv/bin/python elsewhere)
venv\Scripts\python -m pip install -r requirements-gpu.txt  # optional: transcription on an NVIDIA GPU without the CUDA toolkit
npm ci && npx vite build
venv\Scripts\python -m lumiere_hoard                         # http://127.0.0.1:5198
```

`python scripts/launch.py` starts it and opens the browser; `python scripts/dev.py` runs the API with reload and the Vite dev server.

Settings (environment): `LUMIERE_PORT` (5198), `LUMIERE_DATA_DIR`, `LUMIERE_FILE_ROOTS` (folders it may read and export to, separated by `;` on Windows), `LUMIERE_ENCODER` (`auto`, `nvenc`, `x264`), `LUMIERE_RENDER_WORKERS` (chunks encoded at once, 3), `LUMIERE_WORKERS` (background jobs at once, 2), `LUMIERE_FFMPEG` / `LUMIERE_FFPROBE`. In the app: speech model, device and language, GPU decoding, export folder, automatic transcription of new media, the model for plans.

## Assistants (MCP)

`mcp_server.py` is a stdio MCP bridge with 32 tools. It never opens the database: every call goes to the running app with the token in `data/mcp-token`, and it starts the app when nothing answers.

```json
{"command": "<repo>/venv/Scripts/python.exe", "args": ["<repo>/mcp_server.py"],
 "env": {"LUMIERE_URL": "http://127.0.0.1:5198", "LUMIERE_TOKEN_FILE": "<repo>/data/mcp-token"}}
```

The tools cover the library (`media_import`, `media_analyze`, `transcript_get`, `highlights_find`…), projects and the timeline (`project_create`, `project_get`, `timeline_edit` with 31 operations, `timeline_history`), smart edits (`edit_command`, `text_cut`, `timeline_transcript`), plans (`plan_create`, `plan_apply`), output (`render_start`, `job_status`, `renders_list`, `frame_snapshot`, `subtitles_export`) and settings. A wrong operation or field gets an answer listing every operation with its fields; `project_get` lists titles first and reads long timelines by track or time window; `frame_snapshot` returns the picture itself (an MCP image) and the layers drawn at that time (titles, captions, media), so an assistant can check its own work. `faustus-plugin.json` describes the app, its launch and the bridge for hosts that read it.

## How it is built

- `lumiere_hoard/timeline.py` — the project document (canvas, tracks, clips, markers, captions; integer milliseconds).
- `lumiere_hoard/ops.py` — the operation vocabulary, applied all or nothing to a copy of the project; the UI, the MCP tools and the plans share it.
- `lumiere_hoard/render/` — the compiler (timeline → per-chunk filter scripts, transitions with `xfade`, titles and captions as one ASS file, the sound graph from FLAC masters), the runner (parallel chunks, loudness, mux, quality check, frames, lossless cut) and the effect table (anything not in it is refused).
- `lumiere_hoard/analysis/` — sound (envelope, silences, loudness, tempo and beats), picture (scenes, motion, the focus track and camera paths), speech (transcription, filler words) and script alignment.
- `lumiere_hoard/commands.py`, `plan.py` — smart edits and plans; `jobs.py` — the background queue (proxies, analyses, transcription, renders) with progress and cancel.
- `client/` — React interface: library, live preview composed in the browser from the proxies, timeline, inspector, text view, assistant, export.

Tests: `python -m pytest -q` (synthetic media made with ffmpeg; renders are checked frame by frame).

## Limits

- The live preview is an approximation drawn by the browser (transitions and effects are simplified); "Exact frame" and the 540p preview export show the real result.
- Speed is constant per clip (split a clip to change speed); no speed curves, nested sequences or multicam.
- Speaker separation is not included; the meaning-based script assembly depends on the local model and is slower than the word-for-word one.
- Face tracking uses OpenCV's classic detectors: good for people facing the camera, weaker in profile or small in the frame.

## Licence

MIT.
