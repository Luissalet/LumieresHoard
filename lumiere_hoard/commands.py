"""Smart edits built on the analysis: remove silences and filler words, cut by transcript, split at scenes, reframe to
vertical, captions, cut to the beat, highlights, loudness matching. Each command takes a Project and returns a new one
plus a summary, so a plan can chain several and save them as one undo step. When an analysis is missing the command
raises NeedsAnalysis with the jobs it queued."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional

import numpy as np

from . import analyze
from . import media as media_store
from . import projects as project_store
from .analysis import audio as audio_an
from .analysis import speech
from .analysis import video as video_an
from .errors import LumiereError, NotFound
from .ops import PRESETS, apply_ops, source_to_timeline
from .timeline import Clip, Project, Reframe
from .util import ms_to_tc

if TYPE_CHECKING:
    from .services import Services


class NeedsAnalysis(LumiereError):
    code = "needs_analysis"

    def __init__(self, message: str, jobs: list[dict[str, Any]]):
        super().__init__(message)
        self.jobs = jobs


def _main_media(p: Project, media: Optional[str]) -> list[str]:
    if media:
        return [media]
    main = p.main_track()
    seen: list[str] = []
    for c in (main.clips if main else []):
        if c.media and c.media not in seen:
            seen.append(c.media)
    return seen


def _need(svc: "Services", media_ids: list[str], kind: str, what: str, **kw) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for mid in media_ids:
        res = media_store.get_analysis(svc, mid, kind)
        if res is None:
            missing.append(mid)
        else:
            found[mid] = res
    if missing:
        jobs = []
        for mid in missing:
            jobs += analyze.schedule(svc, mid, [kind], **kw)
        names = ", ".join(media_store.get(svc, m)["name"] for m in missing)
        raise NeedsAnalysis(f"{what} needs the {kind} of {names}; it is running now (jobs: {', '.join(j.get('job', '') for j in jobs)}). "
                            "Repeat when they finish.", jobs)
    return found


def _apply(svc: "Services", p: Project, ops: list[dict[str, Any]]) -> Project:
    if not ops:
        return p
    new, _ = apply_ops(p, ops, project_store.media_lookup(svc))
    return new


# ---------------------------------------------------------------- silences / fillers / words

def remove_silences(svc: "Services", p: Project, *, media: Optional[str] = None, threshold_db: Optional[float] = None, min_silence_ms: int = 500,
                    margin_ms: int = 150, mode: str = "cut", speed: float = 4.0) -> tuple[Project, dict[str, Any]]:
    before = p.duration
    total_cuts = 0
    for mid in _main_media(p, media):
        info = media_store.get(svc, mid)
        if not info["has_audio"]:
            continue
        s = analyze.silences_for(svc, mid, threshold_db=threshold_db, min_silence_ms=min_silence_ms, margin_ms=margin_ms)
        if not s["ranges"]:
            continue
        if mode == "cut":
            p = _apply(svc, p, [{"op": "cut_source", "media": mid, "ranges": s["ranges"]}])
            total_cuts += s["count"]
        else:
            p = _speed_ranges(svc, p, mid, s["ranges"], speed)
            total_cuts += s["count"]
    return p, {"cuts": total_cuts, "before": ms_to_tc(before), "after": ms_to_tc(p.duration), "saved_ms": before - p.duration, "mode": mode}


def _speed_ranges(svc: "Services", p: Project, media_id: str, ranges: list[list[int]], speed: float) -> Project:
    """Play the given source ranges faster instead of cutting them (split around each one, then speed the middle)."""
    for a, b in sorted(ranges, reverse=True):
        for t0, t1 in reversed(source_to_timeline(p, media_id, [(a, b)])):
            main = p.main_track()
            hit = next((c for t in p.tracks for c in t.clips if c.media == media_id and c.start <= t0 < c.end and not t.locked), None)
            if hit is None or t1 - t0 < 200:
                continue
            ops: list[dict[str, Any]] = []
            if t0 - hit.start > 40:
                ops.append({"op": "split", "clip": hit.id, "at": t0})
            p2, res = apply_ops(p, ops, project_store.media_lookup(svc)) if ops else (p, [])
            middle_id = res[0]["new_clips"][0] if ops else hit.id
            _, mid_clip = p2.find(middle_id)
            ops2: list[dict[str, Any]] = []
            if mid_clip.end - t1 > 40:
                ops2.append({"op": "split", "clip": middle_id, "at": t1})
            ops2.append({"op": "speed", "clip": middle_id, "speed": min(16.0, mid_clip.speed * speed)})
            p = _apply(svc, p2, ops2)
            del main
    return p


def remove_fillers(svc: "Services", p: Project, *, media: Optional[str] = None, extra: Optional[list[str]] = None, repeats: bool = True,
                   strict: bool = False) -> tuple[Project, dict[str, Any]]:
    mids = [m for m in _main_media(p, media) if media_store.get(svc, m)["has_audio"]]
    transcripts = _need(svc, mids, "transcript", "Removing filler words")
    before = p.duration
    found: list[dict[str, Any]] = []
    for mid, t in transcripts.items():
        hits = speech.find_fillers(t["words"], t.get("language") or "es", extra=extra, repeats=repeats, strict=strict)
        if not hits:
            continue
        ids = {i for h in hits for i in h["ids"]}
        ranges = speech.cut_ranges_for_words(t["words"], ids)
        p = _apply(svc, p, [{"op": "cut_source", "media": mid, "ranges": ranges}])
        found += [{"media": mid, "text": h["text"], "at": ms_to_tc(h["t0"]), "reason": h["reason"]} for h in hits]
    return p, {"removed": len(found), "examples": found[:30], "before": ms_to_tc(before), "after": ms_to_tc(p.duration)}


def cut_words(svc: "Services", p: Project, *, media: str, word_ids: Optional[list[str]] = None, text: Optional[str] = None,
              keep: bool = False) -> tuple[Project, dict[str, Any]]:
    """Text-based editing: remove (or keep only) words of a media's transcript by id or by a phrase."""
    t = _need(svc, [media], "transcript", "Editing by text")[media]
    words = t["words"]
    ids: set[str] = set(word_ids or [])
    if text:
        target = [speech.norm(x) for x in text.split() if speech.norm(x)]
        normed = [speech.norm(w["text"]) for w in words]
        hits = 0
        for i in range(len(words) - len(target) + 1):
            if normed[i: i + len(target)] == target:
                ids.update(w["id"] for w in words[i: i + len(target)])
                hits += 1
        if not hits:
            raise NotFound(f"The phrase «{text}» is not in the transcript.")
    if not ids:
        raise LumiereError("Give word ids or a phrase.")
    unknown = ids - {w["id"] for w in words}
    if unknown:
        raise NotFound(f"Unknown word ids: {', '.join(sorted(unknown)[:10])}.")
    before = p.duration
    if keep:
        kept = [w for w in words if w["id"] in ids]
        ranges = []
        for w in kept:
            if ranges and w["t0"] - ranges[-1][1] < 400:
                ranges[-1][1] = w["t1"] + 120
            else:
                ranges.append([max(0, w["t0"] - 120), w["t1"] + 120])
        p = _apply(svc, p, [{"op": "keep_source", "media": media, "ranges": ranges}])
    else:
        p = _apply(svc, p, [{"op": "cut_source", "media": media, "ranges": speech.cut_ranges_for_words(words, ids)}])
    return p, {"words": len(ids), "before": ms_to_tc(before), "after": ms_to_tc(p.duration), "mode": "keep" if keep else "cut"}


def timeline_transcript(svc: "Services", p: Project, *, track: Optional[str] = None) -> dict[str, Any]:
    """The words heard on the timeline, in timeline order, with their timeline times and their media / word ids — what a text
    editor shows. Media without a transcript are listed in ``missing``."""
    t = p.track(track) if track else p.main_track()
    if t is None:
        return {"words": [], "missing": []}
    out: list[dict[str, Any]] = []
    missing: list[str] = []
    cache: dict[str, Optional[dict]] = {}
    for c in sorted(t.clips, key=lambda c: c.start):
        if c.type != "media" or c.reverse:
            continue
        if c.media not in cache:
            cache[c.media] = analyze.transcript(svc, c.media)
        tr = cache[c.media]
        if tr is None:
            if c.media not in missing and media_store.get(svc, c.media)["has_audio"]:
                missing.append(c.media)
            continue
        for w in tr["words"]:
            mid = (w["t0"] + w["t1"]) / 2
            if c.src_in <= mid < c.src_out:
                out.append({"id": w["id"], "media": c.media, "clip": c.id, "text": w["text"], "t": int(c.timeline_at(w["t0"])),
                            "t1": int(c.timeline_at(w["t1"])), "p": w.get("p")})
    return {"track": t.id, "words": out, "missing": missing}


# ---------------------------------------------------------------- scenes

def split_scenes(svc: "Services", p: Project, *, media: Optional[str] = None, mode: str = "split") -> tuple[Project, dict[str, Any]]:
    mids = [m for m in _main_media(p, media) if media_store.get(svc, m)["has_video"]]
    found = _need(svc, mids, "scenes", "Splitting at scene changes")
    n = 0
    for mid, res in found.items():
        cuts = [c["t"] for c in res.get("cuts", [])]
        for t_src in cuts:
            for t0, _ in source_to_timeline(p, mid, [(t_src, t_src + 1)]):
                if mode == "markers":
                    p = _apply(svc, p, [{"op": "marker_add", "t": t0, "label": "Escena", "kind": "scene", "color": "#3BA4F5"}])
                    n += 1
                else:
                    clip_hit = next((c for t in p.tracks for c in t.clips if c.media == mid and c.start + 40 < t0 < c.end - 40), None)
                    if clip_hit:
                        p = _apply(svc, p, [{"op": "split", "clip": clip_hit.id, "at": t0}])
                        n += 1
    return p, {"scenes": n, "mode": mode}


# ---------------------------------------------------------------- reframe

def aspect_canvas(aspect: str, current: Project) -> dict[str, Any]:
    r = video_an.aspect_of(aspect)
    fps = current.canvas.fps
    if abs(r - 9 / 16) < 0.01:
        return {"width": 1080, "height": 1920, "fps": fps}
    if abs(r - 1) < 0.01:
        return {"width": 1080, "height": 1080, "fps": fps}
    if abs(r - 4 / 5) < 0.01:
        return {"width": 1080, "height": 1350, "fps": fps}
    if abs(r - 16 / 9) < 0.01:
        return {"width": 1920, "height": 1080, "fps": fps}
    h = 1920 if r < 1 else 1080
    w = int(round(h * r / 2)) * 2
    return {"width": w, "height": h, "fps": fps}


def reframe(svc: "Services", p: Project, *, aspect: str = "9:16", mode: str = "auto", clips: Optional[list[str]] = None) -> tuple[Project, dict[str, Any]]:
    """Change the canvas aspect and keep the subject in frame: every horizontal video clip on the main track (or the given
    clips) is cropped with a camera path from the focus analysis (faces, else motion and detail), still within a scene
    when the subject does not move, panning smoothly otherwise. mode: auto | track | stable | center | blur (the whole frame over
    a blurred fill, nothing cropped)."""
    size = aspect_canvas(aspect, p)
    p = _apply(svc, p, [{"op": "canvas", **size}])
    targets: list[Clip] = []
    if clips:
        targets = [p.find(c)[1] for c in clips]
    else:
        main = p.main_track()
        targets = [c for c in (main.clips if main else []) if c.type == "media"]
    out_aspect = size["width"] / size["height"]
    video_ids = sorted({c.media for c in targets if media_store.get(svc, c.media)["has_video"] and media_store.get(svc, c.media)["kind"] == "video"})
    found = _need(svc, video_ids, "focus", "Reframing") if mode not in ("center", "blur") else {}
    scenes: dict[str, list[int]] = {}
    for mid in video_ids:
        sc = media_store.get_analysis(svc, mid, "scenes")
        scenes[mid] = [c["t"] for c in (sc or {}).get("cuts", [])]
        if sc is None and mode not in ("center", "blur"):
            analyze.schedule(svc, mid, ["scenes"])  # better next time; the path still works without cuts
    changed = 0
    ops: list[dict[str, Any]] = []
    for c in targets:
        info = media_store.get(svc, c.media)
        if mode == "blur":
            ops.append({"op": "set", "clip": c.id, "props": {"reframe": None, "transform": {"fit": "blur", "scale": 1.0, "x": 0, "y": 0}}})
            changed += 1
            continue
        ops.append({"op": "set", "clip": c.id, "props": {"transform": {"fit": "cover", "scale": 1.0, "x": 0, "y": 0}}})
        if info["kind"] != "video" or mode == "center":
            ops.append({"op": "set", "clip": c.id, "props": {"reframe": None, "transform": {"focus_x": 0.5, "focus_y": 0.5}}})
            changed += 1
            continue
        in_aspect = info["width"] / max(1, info["height"])
        samples = [s for s in found[c.media]["samples"] if c.src_in - 2000 <= s[0] <= c.src_out + 2000]
        path = video_an.smooth_path(samples, scenes.get(c.media, []), aspect_in=in_aspect, aspect_out=out_aspect,
                                    mode=mode if mode in ("track", "stable") else "auto")
        if path:
            ops.append({"op": "set", "clip": c.id, "props": {"reframe": Reframe(path=path, mode="track" if mode == "auto" else mode).model_dump()}})
        changed += 1
    p = _apply(svc, p, ops)
    faces = any(found[m].get("faces") for m in found) if found else False
    return p, {"canvas": f"{size['width']}x{size['height']}", "clips": changed, "mode": mode, "detector": "faces+saliency" if faces else "saliency"}


# ---------------------------------------------------------------- captions

def captions(svc: "Services", p: Project, *, enabled: bool = True, style: Optional[str] = None, props: Optional[dict[str, Any]] = None,
             language: str = "") -> tuple[Project, dict[str, Any]]:
    op: dict[str, Any] = {"op": "captions", "enabled": enabled, "props": props or {}}
    if style:
        op["style"] = style
    p = _apply(svc, p, [op])
    if enabled:
        tracks = p.captions.tracks or ([p.main_track().id] if p.main_track() else [])
        mids = sorted({c.media for t in p.tracks if t.id in tracks for c in t.clips if c.media and media_store.get(svc, c.media)["has_audio"]})
        _need(svc, mids, "transcript", "Captions", language=language)
    return p, {"captions": p.captions.model_dump()}


# ---------------------------------------------------------------- beat sync

def beat_sync(svc: "Services", p: Project, *, music: str, source: Optional[str] = None, beats_per_cut: int = 2, start_ms: int = 0,
              length_ms: Optional[int] = None, mode: str = "scenes") -> tuple[Project, dict[str, Any]]:
    """Rebuild the main track as cuts on the beat of ``music``: each cut lasts ``beats_per_cut`` beats. The pictures come from
    the main track's clips in order (mode=clips) or from the scenes of ``source`` (mode=scenes), each starting at its scene."""
    beats = _need(svc, [music], "beats", "Cutting to the beat")[music]
    grid = [b for b in beats.get("beats", []) if b >= start_ms]
    if len(grid) < 2:
        raise LumiereError("No beat grid found in that music.")
    music_info = media_store.get(svc, music)
    end_limit = start_ms + (length_ms or music_info["duration_ms"])
    grid = [b for b in grid if b <= end_limit]
    step = max(1, int(beats_per_cut))
    cuts = grid[::step]
    if len(cuts) < 2:
        raise LumiereError("The music is too short for that many beats per cut.")
    segments: list[tuple[str, int]] = []  # (media, src_in)
    main = p.main_track()
    if mode == "clips" or not source:
        pool = [c for c in (main.clips if main else []) if c.type == "media"]
        if not pool:
            raise LumiereError("The main track is empty: add clips or give a source video.")
        segments = [(c.media, c.src_in) for c in pool]
    else:
        info = media_store.get(svc, source)
        sc = _need(svc, [source], "scenes", "Cutting to the beat")[source]
        starts = [0] + [c["t"] for c in sc.get("cuts", [])]
        segments = [(source, s) for s in starts if s < info["duration_ms"] - 500]
    first_beat = cuts[0]
    new_clips: list[dict[str, Any]] = []
    look = project_store.media_lookup(svc)
    for i, (a, b) in enumerate(zip(cuts, cuts[1:])):
        mid, src_in = segments[i % len(segments)]
        info = look(mid) or {}
        length = b - a
        if info.get("kind") == "image":
            new_clips.append({"media": mid, "length": length})
            continue
        dur = int(info.get("duration_ms") or 0)
        lap = i // len(segments)
        s = src_in + lap * length
        if dur and s + length > dur:
            s = max(0, dur - length)
        new_clips.append({"media": mid, "src_in": s, "src_out": s + length})
    ops: list[dict[str, Any]] = []
    if main is not None and main.clips:
        ops.append({"op": "delete", "clips": [c.id for c in main.clips], "ripple": False})
    music_track = next((t for t in p.tracks if t.kind == "audio" and t.role == "music"), None)
    if music_track is None:
        ops.append({"op": "track_add", "kind": "audio", "name": "Música", "role": "music", "id": "trk_music"})
        music_track_id = "trk_music"
    else:
        music_track_id = music_track.id
        if music_track.clips:
            ops.append({"op": "delete", "clips": [c.id for c in music_track.clips], "ripple": False})
    p = _apply(svc, p, ops)
    main = p.main_track()
    if main is None:
        p = _apply(svc, p, [{"op": "track_add", "kind": "video", "name": "Principal", "role": "main"}])
        main = p.main_track()
    p = _apply(svc, p, [{"op": "sequence", "track": main.id, "items": new_clips},
                        {"op": "add_media", "media": music, "track": music_track_id, "at": 0, "src_in": first_beat, "src_out": cuts[-1], "mode": "overwrite"}])
    for t in p.tracks:
        if t.id == music_track_id:
            t.duck = False
    return p, {"cuts": len(new_clips), "bpm": beats.get("bpm"), "beats_per_cut": step, "length": ms_to_tc(cuts[-1] - first_beat)}


# ---------------------------------------------------------------- highlights

def highlights(svc: "Services", media: str, *, count: int = 5, length_ms: int = 30000, min_gap_ms: int = 20000,
               use_transcript: bool = True) -> dict[str, Any]:
    """The most eventful windows of a long video: loud moments and sudden peaks in the sound, lots of motion, many scene
    changes, and (with a transcript) dense speech with exclamations. Returns ranked windows with the reasons."""
    info = media_store.get(svc, media)
    dur = info["duration_ms"]
    secs = max(1, dur // 1000)
    score = np.zeros(secs, dtype=np.float64)
    reasons: list[list[str]] = [[] for _ in range(secs)]
    levels = media_store.rms(svc, media)
    if levels is not None and levels.size:
        e = audio_an.energy_per_second(levels)[:secs]
        z = (e - np.median(e)) / (np.std(e) + 1e-6)
        peak = np.zeros_like(z)
        peak[1:] = np.maximum(0, np.diff(e))
        pz = (peak - peak.mean()) / (peak.std() + 1e-6)
        score[: z.size] += np.clip(z, -2, 4) * 1.0 + np.clip(pz, 0, 4) * 0.6
        for i in np.flatnonzero(z > 1.5):
            if i < secs:
                reasons[i].append("loud")
    motion = media_store.get_analysis(svc, media, "motion")
    if motion is None and info["has_video"]:
        analyze.schedule(svc, media, ["motion"])
    elif motion:
        m = np.array(motion["per_second"][:secs], dtype=np.float64)
        mz = (m - np.median(m)) / (np.std(m) + 1e-6)
        score[: mz.size] += np.clip(mz, -2, 4) * 0.8
        for i in np.flatnonzero(mz > 1.5):
            if i < secs:
                reasons[i].append("motion")
    sc = media_store.get_analysis(svc, media, "scenes")
    if sc:
        for c in sc.get("cuts", []):
            i = c["t"] // 1000
            if i < secs:
                score[i] += 0.5
                reasons[i].append("cut")
    tr = media_store.get_analysis(svc, media, "transcript") if use_transcript else None
    if tr:
        for w in tr["words"]:
            i = w["t0"] // 1000
            if i < secs:
                score[i] += 0.08 + (0.6 if w["text"].endswith("!") else 0)
                if w["text"].endswith("!"):
                    reasons[i].append("exclamation")
    win = max(3, length_ms // 1000)
    if secs <= win:
        return {"media": media, "highlights": [{"start_ms": 0, "end_ms": dur, "score": 0, "reasons": []}], "signals": _signals(levels, motion, sc, tr)}
    kernel = np.ones(win) / win
    smooth = np.convolve(score, kernel, mode="valid")
    picked: list[dict[str, Any]] = []
    order = np.argsort(-smooth)
    gap = max(win, min_gap_ms // 1000)
    for i in order:
        if len(picked) >= count:
            break
        if any(abs(int(i) - p["_i"]) < gap for p in picked):
            continue
        rs: dict[str, int] = {}
        for r in reasons[int(i): int(i) + win]:
            for x in r:
                rs[x] = rs.get(x, 0) + 1
        start = int(i) * 1000
        # start on a sentence boundary when there is a transcript
        if tr:
            prev = [w for w in tr["words"] if w["t1"] <= start + 1500 and w["t0"] >= start - 6000]
            for a, b in zip(prev, prev[1:]):
                if b["t0"] - a["t1"] > 500 and abs(b["t0"] - start) < 4000:
                    start = b["t0"] - 150
        picked.append({"_i": int(i), "start_ms": max(0, start), "end_ms": min(dur, start + length_ms), "score": round(float(smooth[i]), 3),
                       "reasons": sorted(rs, key=lambda k: -rs[k])[:4]})
    for x in picked:
        x.pop("_i")
        x["range"] = f"{ms_to_tc(x['start_ms'])}–{ms_to_tc(x['end_ms'])}"
    return {"media": media, "highlights": picked, "signals": _signals(levels, motion, sc, tr)}


def _signals(levels, motion, scenes, tr) -> list[str]:
    out = []
    if levels is not None:
        out.append("sound")
    if motion:
        out.append("motion")
    if scenes:
        out.append("scenes")
    if tr:
        out.append("transcript")
    return out


# ---------------------------------------------------------------- loudness matching

def match_loudness(svc: "Services", p: Project, *, target_lufs: float = -16.0, track: Optional[str] = None) -> tuple[Project, dict[str, Any]]:
    """Set each clip's gain so every source sits at the same loudness (dialogue from different mics, game captures)."""
    tracks = [p.track(track)] if track else [t for t in p.tracks if t.kind in ("video", "audio") and t.role != "music"]
    mids = sorted({c.media for t in tracks for c in t.clips if c.media and media_store.get(svc, c.media)["has_audio"]})
    found = _need(svc, mids, "loudness", "Matching loudness")
    ops = []
    for t in tracks:
        for c in t.clips:
            res = found.get(c.media or "")
            if not res or res.get("integrated_lufs") is None:
                continue
            gain = max(-20.0, min(20.0, target_lufs - float(res["integrated_lufs"])))
            ops.append({"op": "set", "clip": c.id, "props": {"volume_db": round(gain, 1)}, "ripple": False})
    p = _apply(svc, p, ops)
    return p, {"clips": len(ops), "target_lufs": target_lufs}


# ---------------------------------------------------------------- zoom on cuts

def zoom_cuts(svc: "Services", p: Project, *, scale: float = 1.12, every: int = 2, track: Optional[str] = None) -> tuple[Project, dict[str, Any]]:
    """The talking-head trick: alternate framings across jump cuts (every ``every``-th clip punched in by ``scale``) so the
    cuts read as camera changes."""
    if not 1.0 <= scale <= 2.0:
        raise LumiereError("scale goes from 1.0 to 2.0.")
    t = p.track(track) if track else p.main_track()
    if t is None:
        raise LumiereError("No video track.")
    clips = [c for c in sorted(t.clips, key=lambda c: c.start) if c.type == "media"]
    ops = []
    for i, c in enumerate(clips):
        target = scale if every > 0 and i % max(1, every) == max(1, every) - 1 else 1.0
        if abs(c.transform.scale - target) > 1e-3:
            ops.append({"op": "set", "clip": c.id, "props": {"transform": {"scale": target}}, "ripple": False})
    p = _apply(svc, p, ops)
    return p, {"clips": len(ops), "scale": scale, "every": every}


# ---------------------------------------------------------------- script assembly

def _meaning_alignment(svc: "Services", media: str, segments: list, transcript: dict[str, Any]) -> dict[str, Any]:
    """Ask the local model which sentences of a free talk deliver each script part (cached per script text)."""
    import hashlib

    from .generate import chat_json

    sents = [s for s in transcript.get("segments") or [] if s.get("text")]
    if not sents:
        raise LumiereError("The transcript has no sentences.")
    key = hashlib.sha1(("\n".join(s.text for s in segments) + f"|{len(sents)}").encode()).hexdigest()
    cached = media_store.get_analysis(svc, media, "script_align")
    if cached and cached.get("key") == key:
        return cached
    lines = [f"{i}\t{ms_to_tc(s['t0'])}\t{s['text']}" for i, s in enumerate(sents)]
    script_lines = [f"{seg.index + 1}. {seg.title}: {seg.text}" for seg in segments]
    system = ("You align a talk recorded in front of a camera to the script it follows freely. For each script part, give the sentence "
              "ranges of the recording that deliver it, in the order to play them. When a part was attempted several times, keep only the "
              "last attempt that reaches its end. Leave out false starts, comments to the camera crew or to oneself ('vamos allá', 'otra "
              "vez', 'qué nervios'), and anything that belongs to no part. A part that was never said gets no ranges. Answer JSON only: "
              '{"parts": [{"segment": 1, "ranges": [[first_sentence, last_sentence], ...]}], "notes": ""}')
    user = "SCRIPT\n" + "\n".join(script_lines) + "\n\nRECORDING (index, time, sentence)\n" + "\n".join(lines)
    if len(user) > 60000:
        raise LumiereError("The recording is too long for the model to align at once; cut it into parts first.")

    def parse(data: Any, strict: bool) -> dict[str, Any]:
        parts = data.get("parts") if isinstance(data, dict) else None
        if not isinstance(parts, list):
            raise ValueError("missing parts")
        out = []
        for part in parts:
            seg = int(part.get("segment"))
            ranges = []
            for r in part.get("ranges") or []:
                x, y = int(r[0]), int(r[1])
                if not (0 <= x <= y < len(sents)):
                    raise ValueError(f"sentence range {r} out of bounds")
                ranges.append([x, y])
            out.append({"segment": seg, "ranges": ranges})
        return {"parts": out, "notes": str(data.get("notes") or "")}

    result, model = chat_json(svc, [{"role": "system", "content": system}, {"role": "user", "content": user}], parse, max_tokens=3000, effort="off")
    result.update({"key": key, "model": model, "sentences": [[s["t0"], s["t1"]] for s in sents]})
    media_store.put_analysis(svc, media, "script_align", result, {"segments": len(segments)})
    return result


def script_assemble(svc: "Services", p: Project, *, media: str, script: str = "", script_path: str = "", take: str = "last",
                    min_coverage: float = 0.6, markers: bool = True, mode: str = "auto") -> tuple[Project, dict[str, Any]]:
    """Rough cut from a script: the recording becomes the main track, one take per script segment in script order, with a
    chapter marker per segment. mode words: matches the script word for word (teleprompter readings, retakes); meaning: the
    local model finds each part in a talk that follows the script freely; auto: words, then meaning when words find too little.
    take: last | best (words mode)."""
    from pathlib import Path

    from .analysis import script as script_an

    if script_path and not script:
        path = Path(script_path).expanduser()
        media_store._check_root(svc, path)
        if not path.is_file():
            raise NotFound(f"There is no script at {path}.")
        script = path.read_text(encoding="utf-8", errors="replace")
    segments = script_an.parse_script(script)
    if not segments:
        raise LumiereError("The script has no text: paste it (Markdown with ## sections, a plan JSON or paragraphs).")
    transcript = _need(svc, [media], "transcript", "Assembling from the script")[media]
    words = transcript["words"]
    if not words:
        raise LumiereError("The transcript of that recording is empty: is there speech in it?")
    items: list[dict[str, Any]] = []
    used_mode = "words"
    missing: list[dict[str, Any]] = []
    notes = ""
    res = script_an.assemble(segments, words, take="best" if take == "best" else "last", min_coverage=min_coverage) if mode != "meaning" else None
    if res is not None and (mode == "words" or len(res["segments"]) * 2 > len(segments)):
        if not res["segments"]:
            best = 0.0
            tokens = [speech.norm(w["text"]) for w in words]
            for seg in segments[:12]:
                for t in script_an.find_takes(seg, words, tokens, min_coverage=0.0, max_takes=1):
                    best = max(best, t["coverage"])
            raise LumiereError(f"No segment of the script was found word for word in the recording (best match {round(best * 100)}% of a "
                               "segment's words). This mode is for recordings read from the script or a teleprompter; for a talk that "
                               "follows the script freely use mode='meaning' (the local model finds each part).", code="script_not_found")
        for s in res["segments"]:
            items.append({"segment": s["segment"], "title": s["title"], "ranges": [[s["src_in"], s["src_out"]]], "takes": s["takes"],
                          "coverage": s["coverage"]})
        missing = res["missing"]
    else:
        used_mode = "meaning"
        align = _meaning_alignment(svc, media, segments, transcript)
        sents = align["sentences"]
        by_seg = {part["segment"]: part["ranges"] for part in align["parts"]}
        notes = align.get("notes", "")
        for seg in segments:
            ranges = by_seg.get(seg.index + 1) or []
            if not ranges:
                missing.append({"segment": seg.index + 1, "title": seg.title, "text": seg.text[:120]})
                continue
            src = []
            for x, y in ranges:
                a = max(0, sents[x][0] - 150)
                b = sents[y][1] + 250
                if x > 0:
                    a = max(a, sents[x - 1][1])
                if y + 1 < len(sents):
                    b = min(b, max(sents[y + 1][0], sents[y][1]))
                src.append([a, b])
            items.append({"segment": seg.index + 1, "title": seg.title, "ranges": src, "takes": None, "coverage": None})
    if not items:
        raise LumiereError("No part of the script was found in the recording.", code="script_not_found")
    main = p.main_track()
    ops: list[dict[str, Any]] = []
    if main is not None and main.clips:
        ops.append({"op": "delete", "clips": [c.id for c in main.clips], "ripple": False})
    ops.append({"op": "marker_delete", "kind": "chapter"})
    p = _apply(svc, p, ops)
    main = p.main_track()
    seq = [{"media": media, "src_in": a, "src_out": b, "label": it["title"][:120]} for it in items for a, b in it["ranges"]]
    p = _apply(svc, p, [{"op": "sequence", "track": main.id if main else None, "items": seq}])
    if markers:
        cursor = 0
        mops = []
        for it in items:
            mops.append({"op": "marker_add", "t": cursor, "label": it["title"][:120], "kind": "chapter", "color": "#7FE3A0"})
            cursor += sum(b - a for a, b in it["ranges"])
        p = _apply(svc, p, mops)
    summary = {"mode": used_mode, "segments": len(items), "of": len(segments), "missing": missing, "duration": ms_to_tc(p.duration), "notes": notes,
               "retakes": sum(max(0, (it["takes"] or 1) - 1) for it in items),
               "chosen": [{"segment": it["segment"], "title": it["title"],
                           "at": ", ".join(f"{ms_to_tc(a)}–{ms_to_tc(b)}" for a, b in it["ranges"]), "takes": it["takes"],
                           "coverage": it["coverage"]} for it in items]}
    return p, summary


# ---------------------------------------------------------------- registry

def short_from_range(svc: "Services", media: str, start_ms: int, end_ms: int, *, name: str, preset: str = "reels", reframe_mode: str = "auto",
                     with_captions: bool = True) -> dict[str, Any]:
    """A new vertical project from one range of a long video (for highlights): reframed and with captions when available."""
    proj = project_store.create(svc, name, preset=preset)
    pid = proj["id"]
    project_store.edit(svc, pid, [{"op": "add_media", "media": media, "src_in": start_ms, "src_out": end_ms}], label="Fragmento", actor="tool")
    notes = []
    p = project_store.doc(svc, pid)
    try:
        p, _ = reframe(svc, p, aspect=f"{PRESETS[preset]['width']}:{PRESETS[preset]['height']}", mode=reframe_mode)
    except NeedsAnalysis as need:
        notes.append(str(need))
    if with_captions:
        try:
            p, _ = captions(svc, p, enabled=True, style="pop")
        except NeedsAnalysis as need:
            p = _apply(svc, p, [{"op": "captions", "enabled": True, "style": "pop"}])
            notes.append(str(need))
    project_store.save(svc, pid, p, "Corto automático", actor="tool")
    return {"project": pid, "notes": notes}


COMMANDS: dict[str, Callable[..., tuple[Project, dict[str, Any]]]] = {
    "remove_silences": remove_silences, "remove_fillers": remove_fillers, "cut_words": cut_words, "split_scenes": split_scenes,
    "reframe": reframe, "captions": captions, "beat_sync": beat_sync, "match_loudness": match_loudness, "script_assemble": script_assemble,
    "zoom_cuts": zoom_cuts,
}


def run(svc: "Services", project_id: str, name: str, args: dict[str, Any], *, actor: str = "ui", preview: bool = False) -> dict[str, Any]:
    fn = COMMANDS.get(name)
    if fn is None:
        raise LumiereError(f"Unknown command {name!r}. Known: {', '.join(COMMANDS)}.")
    p = project_store.doc(svc, project_id)
    before = p.duration
    try:
        new, summary = fn(svc, p, **args)
    except TypeError as error:
        raise LumiereError(f"{name}: {error}") from error
    if preview:
        return {"project": project_id, "preview": True, "summary": summary, "duration_before": ms_to_tc(before), "duration_after": ms_to_tc(new.duration)}
    label = {"remove_silences": "Quitar silencios", "remove_fillers": "Quitar muletillas", "cut_words": "Editar por texto",
             "split_scenes": "Cortar por escenas", "reframe": "Reencuadre", "captions": "Subtítulos", "beat_sync": "Corte al ritmo",
             "match_loudness": "Igualar volumen", "script_assemble": "Montaje desde guion", "zoom_cuts": "Zoom en los cortes"}[name]
    rev = project_store.save(svc, project_id, new, label, actor)
    return {"project": project_id, "rev": rev, "summary": summary, "duration": ms_to_tc(new.duration), "duration_ms": new.duration}
