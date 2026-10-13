# Incorporated creative engines

Lumiere owns the source of its motion compositor and editing engine under `native/`.
The linked core includes project models, codecs, layers, masks, keyframes, effects,
expressions, scripts, editing commands, graphics, captions and interchange. The two
private workers instantiate these engines in-process. They do not connect to another
application, look for a portable bundle, or read external executable configuration.

Build with Rust1.95.0: `python native/build.py`. The product runs the resulting
`native/bin/lumiere-compositor` and `native/bin/lumiere-editor` (`.exe` on Windows).
See `native/README.md` and `native/PROVENANCE.md` for architecture, copied revisions,
retained licenses and the local codec base. Standard Rust libraries are locked.

The runtime identifiers are `motion` and `edit`. They expose 21 and nine headless
operations respectively. Commands and schemas come from the linked engine itself;
desktop UI operations previously advertised by an external adapter are not exposed
as if an external window were available. Copying the full core does not prove parity
with every historical desktop interaction or optional downloaded modality model.

| API | Capability |
| --- | --- |
| GET /api/creative/status | incorporated engines and build availability |
| GET /api/creative | saved catalogue, engine/timeline filters and individual read errors |
| GET /api/creative/tools/motion or /edit | own operation catalogue and schemas |
| POST /api/creative/title-card | text layers, four opacity keys, editable source and PNG |
| POST /api/creative/film-sequence | copied source media, editable sequence and native H264 |
| POST /api/creative/{id}/call | operate on saved source with a batch of native actions |
| POST /api/creative/{id}/render-video | native motion render plus actual ffprobe validation |
| GET /api/creative/{id}/preview, /project, /render | own PNG, project or video |

Public MCP uses the same service: creative_tools, creative_call, creative_title_card,
creative_film_sequence, creative_render_title_video, creative_list and creative_get.
The catalogue and artifact links reopen saved projects in the browser after reload.
No external MCP process is
used inside this workflow. The private worker protocol is lumiere-worker/1.

Projects retain stable IDs and optional ordinary Lumiere project links. New source
files use `.lumotion` or `.lumedit` and editing has its own lumiere-edit.project tag.
Reading a historical project creates a separate own-format copy; the original source
file and copied media remain unchanged. That importer is frozen to preserve existing
data, without following upstream format changes. Subsequent edits operate on the own
copy. Selection and in-memory undo remain within one batch; source content persists.

Motion rendering captures a separate source snapshot and reads its dimensions, fps and duration,
uses the own render queue and pure-Rust H264 encoder, then verifies codec, dimensions,
duration, fps and decoded frame count. FFmpeg is not the motion encoder; ffprobe is
the existing output verifier. The video returns through media_receive into Lumiere's
existing library and timeline. HTML animation remains a separate incorporated flow
with exact-time seek and source revisions; see HTML_MOTION.md.

The snapshot, video and refreshed PNG keep their source SHA-256. Concurrent native edits
remain saved and their metadata is preserved when an export finishes. Artifact links remain
available if their source is older; get/browser report that difference and offer motion
re-export. These hashes identify the source file, without promising to track manual changes
to every external media resource. The ordinary catalogue now has64 MCP tools.
