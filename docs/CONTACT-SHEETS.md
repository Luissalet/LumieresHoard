# Timeline contact sheets

`project_contact_sheet(project, mode="overview", count=12, width=320,
times=None, show=true)` exports a review of the native composited timeline.
`POST /api/projects/{project}/contact-sheet` takes the same options without
`project` or `show`; it returns text and artifact links. The audited MCP path
is the existing `POST /api/agent/call` with name `project_contact_sheet`.
The stdio bridge discovers its schema automatically. `show=false` keeps MCP
text only; `true` also returns the JPEG image.

In the video editor, use **Sheet** in the top bar. Choose Overview, Cuts or Adaptive,
set the frame count and tile width, then generate. The dialog shows the sheet,
actual timecodes and layer provenance, with downloads for PNG and the JSON
receipt and a link to the portable HTML page.

Overview selects 2–16 frames uniformly across the native output-frame grid,
ending on the last valid frame. It does not target clip starts: a sample can
land inside a clip. The JSON receipt records `sampling_policy.strategy`,
the requested and selected frame counts, and each `frames[].sampling.grid_indices`
list. If a short timeline maps multiple points from the requested grid onto one
output frame, that frame records every original grid index. For each visible clip layer,
`layers[].timeline_position` (`clip_start`, `clip_interior`, `clip_end`, or
`clip_start_end`) plus `clip_timing` with exact timeline bounds, output-grid
frames, and distance from the clip edges. These fields make a uniform sample
distinguishable from a clip boundary. Boundaries takes before/at pairs at main
video-track clip starts; `truncated=true` reports starts omitted by the count.
If there are no nonzero main-track starts, the receipt identifies the
`start_and_last_frame_fallback` and its `fallback_reason`. These modes do not
cover every layer/effect change, gap end or source scene.
Explicit `times` accepts 1–16 in-range integer milliseconds; it snaps to the
renderer frame grid, clamps an in-range request rounding to the exclusive end
to the last valid frame, and deduplicates requests on the same frame. Requested
times and actual frame numbers/times remain separate in the receipt. Explicit
requests record duplicate removal and frame-merging counts in
`sampling_policy`; several requested milliseconds may resolve to one output
frame.

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

## Adaptive sampling

`mode="adaptive"` scans low-resolution frames rendered from Lumiere's native
composited timeline, targeting four grid candidates per second, prioritizing
main-track clip starts, and capping the combined pass at 120. Each adjacent
candidate pair receives a score from mean RGB difference
and the fraction of pixels with a channel change of at least 18/255. Consecutive
above-threshold changes form an interval; the selected change sample lies near
the interval midpoint. The sheet reserves timeline endpoints, applies temporal
spacing to change events, and fills remaining slots with candidates farthest
from existing samples. If no score reaches the threshold, it reports that
fallback and spreads samples across the candidate grid. The JSON policy records
every candidate's frame, time, score components, threshold, selection and
fallback reason.
The editor's Adaptive option uses this same API mode; the frame count is the
maximum number of final samples, not the number of low-resolution scan frames.

This examines the composed edit, including titles and overlays, instead of
analyzing source files as if they were the final timeline. It remains a bounded
visual-change heuristic: an event between candidate frames can be missed,
camera motion or animation can score as change, and similar-looking content can
score low. It does not identify semantic scenes, establish continuity, or prove
Drift/FilmCraft parity. The candidate pass invokes the native frame renderer per
sample; it is capped but can take noticeable time on long or complex timelines.

## Reference scope

[PySceneDetect v0.7.1](https://github.com/Breakthrough/PySceneDetect/tree/6ebb72392de8acfb6c539bf15d0aa912ce7ab6b2),
BSD-3-Clause at that pinned release, documents adjacent-frame HSV content
scores, rolling-average adaptive scores, threshold fades and histogram/hash
alternatives in its [detector reference](https://www.scenedetect.com/docs/latest/api/detectors.html). Its detector API accepts
frames, but its ordinary video-input path sees a source file rather than
Lumiere's live edit composite. [FFmpeg's filter documentation](https://ffmpeg.org/ffmpeg-filters.html#select_002c-aselect)
also exposes a scene-change score for selecting frames from an encoded input.
Those are useful algorithm references; Lumiere keeps its native compositor in
the loop. No external detector dependency or Drift code is included.

[Drift's MCP documentation](https://github.com/CutWire-Studios/Drift/blob/17ab04e27076b877fb48e4bc2774d25627d7e761/docs/MCP.md)
at HEAD `17ab04e27076b877fb48e4bc2774d25627d7e761` (observed 2026-10-07) already
documents contact sheets with change, uniform, scene and explicit sampling,
clip/source attribution and beyond-end flags. This feature fills Lumiere's own
batch-review gap; it is not an advantage established over Drift or full editor
parity. Drift's source-scene mode and specific dHash implementation are not
reproduced here. No Drift code is copied. [Spanish guide](CONTACT-SHEETS.es.md).
