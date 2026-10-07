"""Native timeline contact sheets with frame timing and portable provenance."""
from __future__ import annotations

import base64
import hashlib
import html
import json
import math
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageDraw

from . import projects, media, ffmpeg
from .errors import LumiereError
from .render import compiler, runner
from .util import ms_to_tc, new_id


def _revision(project):
    raw = json.dumps(project.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def sample_times(project, *, mode="overview", count=12):
    """Sample real output frames, including the last valid frame, never the end."""
    if project.duration <= 0:
        raise LumiereError("The timeline is empty.")
    if mode not in {"overview", "boundaries"} or type(count) is not int or not 2 <= count <= 16:
        raise LumiereError("mode must be overview or boundaries; count must be 2–16.")
    fps = project.canvas.fps
    last = max(0, compiler.frame_of_ms(project.duration, fps) - 1)
    if mode == "overview":
        frames = sorted(set(round(i * last / (count - 1)) for i in range(count)))
        truncated = False
    else:
        track = project.main_track()
        boundaries = sorted(set(compiler.frame_of_ms(c.start, fps) for c in track.clips
                                if 0 < compiler.frame_of_ms(c.start, fps) <= last)) if track else []
        selected = boundaries[:count // 2]
        frames = sorted(set(frame for boundary in selected for frame in (boundary - 1, boundary))) if selected else sorted({0, last})
        truncated = len(selected) < len(boundaries)
    return [round(frame * 1000 / fps) for frame in frames], truncated


def _layers(svc, project, frame, actual_ms, stack=()):
    out = []
    for track in reversed(project.tracks):
        if track.hidden or track.kind == "audio":
            continue
        for clip in track.clips:
            if not compiler.frame_of_ms(clip.start, project.canvas.fps) <= frame < compiler.frame_of_ms(clip.end, project.canvas.fps):
                continue
            layer = {"track": track.id, "role": track.role, "clip": clip.id, "type": clip.type}
            if clip.type == "text":
                layer["text"] = clip.text
            else:
                source_ms = clip.src_at(actual_ms)
                layer.update(media=clip.media, source_time_ms=source_ms, source_time=ms_to_tc(round(source_ms)),
                             source_time_kind="timeline mapping, not decoder PTS", speed=clip.speed_at(actual_ms), reverse=clip.reverse)
                if clip.type == "sequence":
                    nested = projects.doc(svc, clip.media)
                    layer["sequence_revision"] = _revision(nested)
                    if clip.media not in stack:
                        layer["nested_layers"] = _layers(svc, nested, compiler.frame_of_ms(source_ms, nested.canvas.fps), source_ms, (*stack, clip.media))
                else:
                    info = media.lookup(svc, clip.media)
                    if info:
                        layer.update(media_name=info["name"], source_path=info["path"])
                if clip.transition_in:
                    layer["transition_in"] = clip.transition_in.model_dump(mode="json")
            out.append(layer)
    if project.captions.enabled:
        out.append({"type": "captions", "style": project.captions.style, "note": "Native burned-in captions are rendered; transcript word provenance is not expanded here"})
    return out


def _source_layers(layers):
    for layer in layers:
        yield layer
        yield from _source_layers(layer.get("nested_layers", []))


def create(svc, project_id, *, mode="overview", count=12, width=320, times=None):
    project = projects.doc(svc, project_id)
    if type(width) is not int or not 128 <= width <= 640:
        raise LumiereError("width must be 128–640 pixels.")
    selected, truncated = sample_times(project, mode=mode, count=count)
    if times is not None:
        if not isinstance(times, list) or not 1 <= len(times) <= 16 or any(type(t) is not int or not 0 <= t < project.duration for t in times):
            raise LumiereError("times must contain 1–16 integer milliseconds inside the timeline.")
        selected, truncated = sorted(set(times)), False
    revisions = {project_id: _revision(project)}
    for nested in projects.nested_ids(svc, project_id):
        revisions[nested] = _revision(projects.doc(svc, nested))
    last = max(0, compiler.frame_of_ms(project.duration, project.canvas.fps) - 1)
    requests = {}
    for t in selected:
        frame = min(last, compiler.frame_of_ms(t, project.canvas.fps))
        requests.setdefault(frame, []).append(t)
    rate = Fraction(ffmpeg.fps_fraction(project.canvas.fps))
    columns = min(4, len(requests))
    height = max(1, min(1280, round(width * project.canvas.height / project.canvas.width)))
    gap, label_h = 8, 40
    sheet = Image.new("RGB", (columns * (width + gap) + gap, math.ceil(len(requests) / columns) * (height + label_h + gap) + gap), "#171717")
    draw = ImageDraw.Draw(sheet)
    artifact = new_id("sheet")
    folder = svc.config.renders_dir / "frames"
    folder.mkdir(parents=True, exist_ok=True)
    outputs, frames, sources = [], [], {}
    try:
        for index, (frame, requested) in enumerate(sorted(requests.items())):
            actual_ms = float(frame * 1000 / rate)
            render_ms = min(project.duration - 1, round(frame * 1000 / project.canvas.fps))
            layers = _layers(svc, project, frame, actual_ms)
            try:
                for layer in _source_layers(layers):
                    if layer.get("source_path") and layer["media"] not in sources:
                        source = Path(layer["source_path"])
                        stat = source.stat()
                        sources[layer["media"]] = {"path": str(source), "sha256": _sha(source), "bytes": stat.st_size,
                                                   "mtime_ns": stat.st_mtime_ns}
            except OSError as exc:
                raise LumiereError(f"Contact sheet source is unavailable at output frame {frame} ({ms_to_tc(round(actual_ms))}): {exc}", code="contact_sheet_frame_failed") from exc
            try:
                original_frame = runner.render_frame(svc, project_id, render_ms, width=width, fmt="png")
                frame_bytes = original_frame.read_bytes()
                frame_path = folder / f"{artifact}-{index + 1}.png"
                outputs.append(frame_path)
                frame_path.write_bytes(frame_bytes)
                with Image.open(frame_path) as image:
                    tile = image.convert("RGB")
                    tile.thumbnail((width, height))
            except Exception as exc:
                raise LumiereError(f"Contact sheet failed at output frame {frame} ({ms_to_tc(round(actual_ms))}): {exc}", code="contact_sheet_frame_failed") from exc
            x = gap + (index % columns) * (width + gap) + (width - tile.width) // 2
            y = gap + (index // columns) * (height + label_h + gap) + (height - tile.height) // 2
            sheet.paste(tile, (x, y))
            label_x, label_y = gap + (index % columns) * (width + gap), gap + (index // columns) * (height + label_h + gap) + height + 3
            draw.text((label_x, label_y), f"{ms_to_tc(round(actual_ms))}  f{frame}", fill="#eeeeee")
            names = ", ".join(layer.get("media_name") or layer.get("text") or layer.get("clip", "") for layer in layers)
            draw.text((label_x, label_y + 16), names[:max(12, width // 6)], fill="#bcbcbc")
            frames.append({"t_ms": round(actual_ms), "time": ms_to_tc(round(actual_ms)), "frame": frame,
                           "actual_time_ms": actual_ms, "actual_time_seconds": {"numerator": frame * rate.denominator, "denominator": rate.numerator},
                           "requested_times_ms": requested, "render_time_ms": render_ms, "layers": layers,
                           "frame_path": str(frame_path), "frame_url": "/api/frames/" + frame_path.name,
                           "frame_sha256": hashlib.sha256(frame_bytes).hexdigest(), "tile_rgb_sha256": hashlib.sha256(tile.tobytes()).hexdigest(),
                           "cell_bbox": [x, y, tile.width, tile.height]})
            if any(_revision(projects.doc(svc, pid)) != revision for pid, revision in revisions.items()):
                raise LumiereError("The timeline changed during review; create a fresh contact sheet.")
        for info in sources.values():
            source = Path(info["path"])
            try:
                stat = source.stat()
                changed = stat.st_size != info["bytes"] or stat.st_mtime_ns != info["mtime_ns"] or _sha(source) != info["sha256"]
            except OSError:
                changed = True
            if changed:
                raise LumiereError("A source changed during review; create a fresh contact sheet.")
        png, jpeg, receipt, page = [folder / f"{artifact}.{ext}" for ext in ("png", "jpg", "json", "html")]
        outputs.extend([png, jpeg, receipt, page])
        sheet.save(png)
        sheet.save(jpeg, quality=88)
        out = {"id": artifact, "status": "complete", "project": project_id, "project_revision": revisions[project_id], "project_revisions": revisions,
               "mode": "explicit" if times is not None else mode, "frames": frames, "sources": sources, "truncated": truncated,
               "path": str(jpeg), "url": "/api/frames/" + jpeg.name, "png_path": str(png), "png_url": "/api/frames/" + png.name,
               "receipt_path": str(receipt), "receipt_url": "/api/frames/" + receipt.name, "html_path": str(page), "html_url": "/api/frames/" + page.name,
               "png_sha256": _sha(png), "jpeg_sha256": _sha(jpeg), "canvas": project.canvas.model_dump(mode="json"),
               "fps_fraction": str(rate), "sheet_size": list(sheet.size), "originals_modified": False,
               "limitations": ["Boundaries samples main-track clip starts, not every composite change or source scene.",
                               "Source times are timeline mappings, not decoder PTS; nested sources are attributed to their sequence.",
                               "A sheet does not prove motion/audio continuity or editor parity."]}
        rows = "".join(f"<tr><td>{row['time']}</td><td>{row['frame']}</td><td>{html.escape(', '.join(layer.get('media_name') or layer.get('text') or layer.get('clip', '') for layer in row['layers']))}</td></tr>" for row in frames)
        page.write_text("<!doctype html><html lang='en'><meta charset='utf-8'><title>Timeline contact sheet</title>"
                        "<style>body{font:16px system-ui;background:#171717;color:#eee;margin:24px}img{max-width:100%;height:auto}td,th{padding:8px;text-align:left}table{border-collapse:collapse}</style>"
                        f"<h1>Timeline contact sheet</h1><p>Project {html.escape(project_id)} · revision {revisions[project_id]}</p>"
                        f"<img alt='Timecoded timeline frames' src='data:image/png;base64,{base64.b64encode(png.read_bytes()).decode('ascii')}'>"
                        f"<table><thead><tr><th>Time</th><th>Frame</th><th>Sources / titles</th></tr></thead><tbody>{rows}</tbody></table></html>", encoding="utf-8")
        out["html_sha256"] = _sha(page)
        receipt.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        out["receipt_sha256"] = _sha(receipt)
        return out
    except Exception:
        for output in outputs:
            output.unlink(missing_ok=True)
        raise
