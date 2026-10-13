# HTML motion compositions

The creative workshop on Projects saves editable HTML compositions, reviews exact-time PNG frames and exports silent H.264 MP4 videos. The seven `html_motion_*` tools use the same service. Receive the resulting video with `media_receive` to put it in the ordinary media library or timeline, where sound, cuts, effects and titles remain available.

## Runtime

Install `pip install -e .[motion]`. The renderer uses a locally installed Chromium browser, including the system browser on Windows, or the browser installed by `python -m playwright install chromium`. `LUMIERE_BROWSER_EXECUTABLE` selects an executable explicitly. FFmpeg and FFprobe use the existing application configuration. Browser rendering and H.264 encoding use the CPU; no text model is loaded.

## Composition contract

Provide a complete HTML file with `window.seek(t)`, where `t` is in seconds. The function may return a promise. Calculate every visible property from `t`, including camera, layout and canvas pixels. Draw the whole canvas on every seek. Avoid elapsed wall time, accumulating simulation steps, CSS transitions, live animation loops and unseeded randomness. Embed fonts, images and scripts for a portable composition. Relative assets are not imported with a file picked in the browser; external URLs and absolute file URLs are resolved by the rendering browser and may change independently.

The viewport is the saved width and height, at device scale 1. Fonts and image decoding finish before capture. A missing seek function, image decode failure or script exception is an error visible through REST, MCP and the workshop. A screenshot is a still review; the service does not grade narrative quality or prove that arbitrary user code is deterministic. H.264 4:2:0 requires even canvas dimensions.

Frames are sampled at `n / fps`, for `n = 0 ... ceil(duration * fps) - 1`. Thus a requested 1.1 seconds at 5 fps exports six frames and lasts 1.2 seconds. Output is checked for H.264, canvas, frame rate, decoded frame count and duration. Rendering uses the existing background queue and cancellation control. The export has no audio; HTML Web Audio is not captured. Imported videos or complex asynchronous media seek routines need their own authored readiness handling. The renderer is not a full animation-engine interchange implementation.

## Source revisions and reuse

Each rendering browser runs in an owned child process. Cancelling a job interrupts a pending or non-terminating `seek` and releases the render lane. `LUMIERE_HTML_FRAME_TIMEOUT_S` sets the timeout for browser readiness and each frame (60 seconds by default); a timed-out worker is stopped and its partial export is removed. This does not reduce the composition duration or frame count. The workshop sends the displayed revision when receiving a video, and MCP frame URLs are bound to the revision that produced the PNG.

Each save creates a new revision under `data/creative/html/<composition>/<revision>/`, with the source, settings and SHA-256. Updates require the revision the caller read, so concurrent saves cannot overwrite a newer edit. Restore copies an earlier source and settings into a new revision and keeps all later versions. Change sources through the save API; the stored revision files are snapshots.

A render queues a specific revision. A later save does not change that render's input, and its completed export does not replace the newer revision's current output. Export paths include the job id; earlier completed outputs remain readable through their own URLs. A failed or cancelled export removes only its partial output. The source download keeps the complete HTML; MCP reads source text in character pages with `next_offset`.

## API and MCP

| REST | MCP | Behavior |
| --- | --- | --- |
| `GET /api/html-motion` | `html_motion_list` | Saved compositions and runtime discovery |
| `POST /api/html-motion` | `html_motion_save` | Create or save source and geometry; optional composition and expected revision |
| `GET /api/html-motion/{id}?revision=` | `html_motion_get` | Source and metadata; MCP offset and next_offset paginate the source |
| `GET /api/html-motion/{id}/revisions/{revision}/source` | Source URL from get | Download the complete editable HTML |
| `GET /api/html-motion/{id}/revisions/{revision}/frame?at=` | `html_motion_frame` | PNG at a time in seconds; source and frame hashes, native MCP image |
| `POST /api/html-motion/{id}/render?revision=` | `html_motion_render` | Queue a version-specific MP4; follow `job_status` and `job_cancel` |
| `POST /api/html-motion/restore` | `html_motion_restore` | Earlier revision becomes a new revision |
| `GET /api/html-motion/{id}/revisions/{revision}/render/{job}` | Result render_url | Stream/download one completed export |
| `POST /api/html-motion/{id}/receive` | Existing `media_receive` | Add the current video to the library and optionally to a project |

The workshop keeps text typed during a pending save. A Faustus refresh updates the selected saved composition when its form is clean; a dirty draft stays in the form while the new saved revision is read. The media list refreshes after receiving an export.

## Verified scope

Tests cover source restoration, concurrent saves, invalid geometry, complete source pagination, out-of-order seek and a fresh browser producing identical PNGs, missing and throwing seek functions, queued-revision preservation and two independently authored DOM/canvas compositions. Real native MCP checks include all six tools, an image content block, video export and handoff into the existing timeline. Browser checks exercise save, reopen, frame review, export and library receipt, including the 390-pixel workshop layout.

This is an added motion capability. Existing native creative engines and timeline tools remain available. It does not establish parity with other studios, capture Web Audio, convert arbitrary real-time pages automatically, or measure the autonomy of the global language model.

## Contact sheets

`html_motion_storyboard` / POST /api/html-motion/{composition}/storyboard captures caller-supplied `times` in seconds, or four evenly spaced moments including start/end. The body includes composition and optional revision; omitted revision is captured once before opening the renderer. All original PNGs come from that one revision and browser session. The sheet shows scaled previews and timestamps; the receipt includes exact times and SHA-256 for source, sheet and originals. Source HTML hashing does not freeze external resource changes or certify that user seek code is a pure function.

Images are immutable derived artifacts under the revision: /storyboards/{id}/image and /storyboards/{id}/frames/{index}. GET verifies each image against its receipt and does not rerender the frame. Failed capture publishes no receipt; the owned browser worker closes on errors/timeouts. The saved composition and its source bytes remain unchanged. Each new sheet has a fresh identity; older results stay accessible. Concurrent edits preserve the inspected revision. The UI reports when a displayed sheet uses an earlier revision.

The actual MCP PNG contains the sheet, not a text description. `show=false` returns metadata/links without the image. The same UI lets users download the sheet or individual full-size originals. It does not grade story quality, synthesize missing images, add audio capture or execute a reference application's CLI/MCP.
