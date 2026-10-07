# Timeline contact sheets

`project_contact_sheet(project, mode="overview", count=12, width=320,
times=None, show=true)` exports a review of the native composited timeline.
`POST /api/projects/{project}/contact-sheet` takes the same options without
`project` or `show`; it returns text and artifact links. The audited MCP path
is the existing `POST /api/agent/call` with name `project_contact_sheet`.
The stdio bridge discovers its schema automatically. `show=false` keeps MCP
text only; `true` also returns the JPEG image.

Overview spreads 2–16 samples across the native output frame grid, ending on
the last valid frame. Boundaries takes complete before/after pairs at main
video-track clip starts, reporting `truncated=true` if count cannot cover all
starts. These are not every layer/effect change, gap end or source scene.
Explicit `times` accepts 1–16 in-range integer milliseconds; it snaps to the
renderer frame grid, clamps an in-range request rounding to the exclusive end
to the last valid frame, and deduplicates requests on the same frame. Requested
times and actual frame numbers/times remain separate in the receipt.

Tiles are 128–640 pixels wide; extreme aspect ratios fit within 1280 pixels
of height. Native PNG frames use the same source-resolution timeline renderer
as final exports, including trims, speed/reverse, overlays, titles and captions.
No proxy pixels or source filmstrip substitutes are used. Source time labels
are clip timeline mappings; they are not claims about decoded source PTS.
Nested layers carry their sequence revision and mapped source attribution.
Audio continuity and semantic continuity require other review.

Each call creates JPEG and exact PNG sheets, separate PNG samples, a portable
HTML file with its PNG embedded, and a JSON receipt under `data/renders/frames`.
Returned `url`, `png_url`, `frame_url`, `html_url` and `receipt_url` use the
existing `/api/frames/{name}` download route. Receipt fields include project
and nested-project SHA-256 revisions, rational output times, visible clip/track/
source attribution, source-file hashes, tile rectangles, RGB tile hashes and
artifact hashes. The receipt's own SHA-256 is returned separately.

Project/nested-project changes during sampling and source-file changes before
publication reject the sheet and delete its unpublished sheet/sample/receipt
outputs. Source checks compare bytes as well as file size/timestamp. A missing
source or native renderer failure identifies its output frame and time. The
renderer may retain its ordinary disposable frame cache after a failed review.
No source file, project document, history or live app configuration is changed.

Real tests verify all three cuts of a four-clip trimmed timeline with an audio
track and title overlay: each PNG tile equals its native frame; JPEG colors
agree; an independent full timeline export decoded with ffmpeg at each recorded
frame agrees within codec/resampling tolerance. A numbered source counter checks
speed 2, reverse and final-frame sampling. Repeat generation gives matching sheet
hashes for these deterministic fixtures. API downloads, MCP schema/agent calls,
source/project invariance and rejected mixed revisions/source changes are tested.

## Reference scope

[Drift's MCP documentation](https://github.com/CutWire-Studios/Drift/blob/17ab04e27076b877fb48e4bc2774d25627d7e761/docs/MCP.md)
at HEAD `17ab04e27076b877fb48e4bc2774d25627d7e761` (observed 2026-10-07) already
documents contact sheets with change, uniform, scene and explicit sampling,
clip/source attribution and beyond-end flags. This feature fills Lumiere's own
batch-review gap; it is not an advantage established over Drift or full editor
parity. Change/dHash and source-scene sampling remain unimplemented here. No
Drift code is copied. [Spanish guide](CONTACT-SHEETS.es.md).
