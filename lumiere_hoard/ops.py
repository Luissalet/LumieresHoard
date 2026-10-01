"""Primitive timeline operations. Pure functions over a Project: no files, no database.

Every operation is a JSON object ``{"op": "<name>", ...}``. ``apply_ops`` runs a list of them on a copy of the project
and returns the new project plus one result per operation; if any operation fails nothing changes. The same vocabulary
is used by the editor UI, the MCP tools and the edit plans written by the model.
"""

from __future__ import annotations

from typing import Any, Callable, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from .errors import LumiereError, NotFound
from .timeline import (MIN_CLIP_MS, Canvas, Captions, CaptionStyle, Clip, Crop, Filter, FilterType, Keyframe, KeyProp, Marker, Project,
                       TextStyle, Track, TrackKind, Transform, Transition, TransitionType, clone, snap)
from .util import new_id, parse_time

MediaLookup = Callable[[str], Optional[dict[str, Any]]]

PRESETS: dict[str, dict[str, Any]] = {
    "reels": {"width": 1080, "height": 1920, "fps": 30, "label": "Reels / Shorts / TikTok 9:16"},
    "shorts": {"width": 1080, "height": 1920, "fps": 30, "label": "YouTube Shorts 9:16"},
    "tiktok": {"width": 1080, "height": 1920, "fps": 30, "label": "TikTok 9:16"},
    "youtube": {"width": 1920, "height": 1080, "fps": 30, "label": "YouTube 1080p 16:9"},
    "youtube_60": {"width": 1920, "height": 1080, "fps": 60, "label": "YouTube 1080p60 (gameplay)"},
    "youtube_4k": {"width": 3840, "height": 2160, "fps": 30, "label": "YouTube 4K"},
    "square": {"width": 1080, "height": 1080, "fps": 30, "label": "Cuadrado 1:1"},
    "portrait_4_5": {"width": 1080, "height": 1350, "fps": 30, "label": "Vertical 4:5 (feed)"},
    "cinema": {"width": 1920, "height": 804, "fps": 24, "label": "Cine 2.39:1"},
    "hd720": {"width": 1280, "height": 720, "fps": 30, "label": "720p"},
}


class OpBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


Time = Union[int, float, str]


def _t(value: Time | None) -> Optional[int]:
    if value is None:
        return None
    try:
        return parse_time(value) if isinstance(value, str) else int(round(value))
    except ValueError as error:
        raise LumiereError(str(error)) from error


class AddMedia(OpBase):
    op: Literal["add_media"]
    media: str
    track: Optional[str] = None
    at: Optional[Time] = Field(None, description="Timeline ms; omitted = end of the track.")
    src_in: Optional[Time] = None
    src_out: Optional[Time] = None
    length: Optional[Time] = Field(None, description="Images: how long they stay (default 4000 ms).")
    mode: Literal["insert", "overwrite", "append"] = "append"
    label: str = ""
    fit: Optional[Literal["contain", "cover", "fill", "none"]] = None


class AddText(OpBase):
    op: Literal["add_text"]
    text: str = Field(..., min_length=1, max_length=4000)
    start: Time = 0
    length: Time = 3000
    track: Optional[str] = None
    style: dict[str, Any] = Field(default_factory=dict)
    x: float = 0.0
    y: float = 0.0


class Split(OpBase):
    op: Literal["split"]
    at: Time
    clip: Optional[str] = Field(None, description="Omitted = every clip under 'at' on unlocked tracks.")


class Trim(OpBase):
    op: Literal["trim"]
    clip: str
    src_in: Optional[Time] = None
    src_out: Optional[Time] = None
    length: Optional[Time] = Field(None, description="Text clips / images: new length.")
    ripple: bool = True


class Move(OpBase):
    op: Literal["move"]
    clip: str
    start: Optional[Time] = None
    track: Optional[str] = None


class Delete(OpBase):
    op: Literal["delete"]
    clips: list[str] = Field(..., min_length=1, max_length=2000)
    ripple: bool = True


class DeleteRange(OpBase):
    op: Literal["delete_range"]
    start: Time
    end: Time
    tracks: Optional[list[str]] = Field(None, description="Omitted = every unlocked track.")
    ripple: bool = True


class CutSource(OpBase):
    op: Literal["cut_source"]
    media: str
    ranges: list[list[Time]] = Field(..., min_length=1, max_length=20000, description="[[from_ms, to_ms], ...] in source time.")
    scope: Literal["linked", "all"] = Field("linked", description="linked: tracks holding this media plus text tracks; all: every unlocked track.")
    ripple: bool = True
    min_gap: int = Field(0, ge=0, le=5000, description="Ranges closer than this are merged.")


class KeepSource(OpBase):
    op: Literal["keep_source"]
    media: str
    ranges: list[list[Time]] = Field(..., min_length=1, max_length=20000)
    scope: Literal["linked", "all"] = "linked"


class SetClip(OpBase):
    op: Literal["set"]
    clip: str
    props: dict[str, Any]
    ripple: bool = True


class Speed(OpBase):
    op: Literal["speed"]
    clip: str
    speed: float = Field(..., ge=0.1, le=16)
    ripple: bool = True


class TransitionOp(OpBase):
    op: Literal["transition"]
    clip: Optional[str] = Field(None, description="The clip that receives the transition from the previous one.")
    track: Optional[str] = Field(None, description="With all_cuts: the track.")
    all_cuts: bool = False
    type: Optional[TransitionType] = Field("crossfade", description="null removes it.")
    dur: int = Field(500, ge=40, le=5000)


class FilterAdd(OpBase):
    op: Literal["filter_add"]
    clips: Optional[list[str]] = None
    track: Optional[str] = None
    type: FilterType
    params: dict[str, Any] = Field(default_factory=dict)


class FilterRemove(OpBase):
    op: Literal["filter_remove"]
    clip: str
    type: Optional[FilterType] = None
    index: Optional[int] = None


class TrackAdd(OpBase):
    op: Literal["track_add"]
    kind: TrackKind
    name: str = ""
    role: Optional[Literal["main", "overlay", "voice", "music", "sfx", "titles"]] = None
    index: Optional[int] = None
    id: Optional[str] = None


class TrackSet(OpBase):
    op: Literal["track_set"]
    track: str
    props: dict[str, Any]


class TrackDelete(OpBase):
    op: Literal["track_delete"]
    track: str


class CanvasOp(OpBase):
    op: Literal["canvas"]
    preset: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    background: Optional[str] = None
    fit: Optional[Literal["contain", "cover", "fill"]] = Field(None, description="Also set this fit on every video clip.")
    length_mode: Optional[Literal["main", "longest"]] = Field(None, description="main: the video ends with the main track; longest: with the last clip.")


class MarkerAdd(OpBase):
    op: Literal["marker_add"]
    t: Time
    label: str = ""
    color: str = "#F5B700"
    kind: Literal["note", "beat", "scene", "highlight", "chapter"] = "note"


class MarkerDelete(OpBase):
    op: Literal["marker_delete"]
    id: Optional[str] = None
    kind: Optional[Literal["note", "beat", "scene", "highlight", "chapter"]] = None


class CaptionsOp(OpBase):
    op: Literal["captions"]
    enabled: Optional[bool] = None
    style: Optional[CaptionStyle] = None
    props: dict[str, Any] = Field(default_factory=dict)


class Duplicate(OpBase):
    op: Literal["duplicate"]
    clip: str
    at: Optional[Time] = None


class DetachAudio(OpBase):
    op: Literal["detach_audio"]
    clip: str
    track: Optional[str] = None


class CloseGaps(OpBase):
    op: Literal["close_gaps"]
    track: Optional[str] = None


class ReplaceMedia(OpBase):
    op: Literal["replace_media"]
    clip: str
    media: str


class Sequence(OpBase):
    op: Literal["sequence"]
    items: list[dict[str, Any]] = Field(..., min_length=1, max_length=2000, description="[{media, src_in?, src_out?, length?}] appended in order.")
    track: Optional[str] = None


class KeyframesOp(OpBase):
    op: Literal["keyframes"]
    clip: str
    prop: KeyProp
    keys: list[Keyframe] = Field(default_factory=list, max_length=500, description="Empty list removes the animation.")


class Notes(OpBase):
    op: Literal["notes"]
    text: str = Field("", max_length=8000)


Op = Union[AddMedia, AddText, Split, Trim, Move, Delete, DeleteRange, CutSource, KeepSource, SetClip, Speed, TransitionOp, FilterAdd,
           FilterRemove, TrackAdd, TrackSet, TrackDelete, CanvasOp, MarkerAdd, MarkerDelete, CaptionsOp, Duplicate, DetachAudio, CloseGaps,
           ReplaceMedia, Sequence, KeyframesOp, Notes]
_ADAPTER = TypeAdapter(Op)
OP_NAMES = sorted(m.model_fields["op"].annotation.__args__[0] for m in Op.__args__)  # type: ignore[union-attr]


def parse_op(raw: dict[str, Any]) -> BaseModel:
    if not isinstance(raw, dict) or "op" not in raw:
        raise LumiereError("Each operation is an object with an 'op' field.")
    if raw["op"] not in OP_NAMES:
        raise LumiereError(f"Unknown operation {raw['op']!r}. Known: {', '.join(OP_NAMES)}.", code="unknown_op")
    try:
        return _ADAPTER.validate_python(raw)
    except ValidationError as error:
        issues = "; ".join(f"{'.'.join(str(p) for p in e['loc'][1:]) or 'input'}: {e['msg']}" for e in error.errors())
        raise LumiereError(f"{raw['op']}: {issues}") from error


# ------------------------------------------------------------------ helpers

class Ctx:
    def __init__(self, project: Project, media: MediaLookup):
        self.p = project
        self.media_lookup = media

    def media(self, media_id: str) -> dict[str, Any]:
        info = self.media_lookup(media_id)
        if info is None:
            raise NotFound(f"No media {media_id}. Import it first (media_import).")
        return info

    def fps(self) -> float:
        return self.p.canvas.fps

    def snap(self, ms: float) -> int:
        return snap(ms, self.fps())


def _unlocked(track: Track) -> None:
    if track.locked:
        raise LumiereError(f"Track {track.name or track.id} is locked.", code="track_locked")


def _track_end(track: Track) -> int:
    return max((c.end for c in track.clips), default=0)


def _shift(track: Track, after: int, delta: int, exclude: set[str] = frozenset()) -> None:
    """Move every clip of ``track`` that starts at or after ``after`` by ``delta`` ms."""
    if not delta:
        return
    for c in track.clips:
        if c.id not in exclude and c.start >= after:
            c.start = max(0, c.start + delta)


def _default_track(ctx: Ctx, info: dict[str, Any]) -> Track:
    p = ctx.p
    if info.get("kind") == "audio":
        for role in ("music", "voice", "sfx"):
            for t in p.tracks:
                if t.kind == "audio" and t.role == role and not t.locked:
                    return t
        t = Track(kind="audio", name="Audio", role="music")
        p.tracks.append(t)
        return t
    main = p.main_track()
    if main is None:
        main = Track(kind="video", name="Principal", role="main")
        p.tracks.insert(0, main)
    return main


def _media_span(ctx: Ctx, info: dict[str, Any], src_in: Optional[int], src_out: Optional[int], length: Optional[int]) -> tuple[int, int]:
    if info.get("kind") == "image":
        span = length if length is not None else (src_out - (src_in or 0) if src_out is not None else 4000)
        if span < MIN_CLIP_MS:
            raise LumiereError("An image needs at least 40 ms on the timeline.")
        return 0, int(span)
    dur = int(info.get("duration_ms") or 0)
    a = 0 if src_in is None else src_in
    b = dur if src_out is None else src_out
    if dur:
        b = min(b, dur)
    if a < 0 or b - a < MIN_CLIP_MS:
        raise LumiereError(f"Empty or too short source range [{a}, {b}] for a {dur} ms media.")
    return a, b


def _clear_range(track: Track, start: int, end: int, keep: set[str] = frozenset()) -> None:
    """Remove [start, end) from a track without moving anything (overwrite / non-ripple delete)."""
    out: list[Clip] = []
    for c in track.clips:
        if c.id in keep or c.end <= start or c.start >= end:
            out.append(c)
            continue
        if c.start < start:
            left = _cut_clip(c, c.start, start)
            if left:
                out.append(left)
        if c.end > end:
            right = _cut_clip(c, end, c.end, new_id_for_part=c.start < start)
            if right:
                out.append(right)
    track.clips = out


def _cut_clip(c: Clip, t0: int, t1: int, new_id_for_part: bool = False) -> Optional[Clip]:
    """The part of clip ``c`` shown between timeline t0 and t1 (a copy)."""
    t0, t1 = max(t0, c.start), min(t1, c.end)
    if t1 - t0 < MIN_CLIP_MS // 2:
        return None
    part = c.model_copy(deep=True)
    if new_id_for_part:
        part.id = new_id("clp")
    part.start = t0
    if c.type == "text":
        part.length = t1 - t0
    else:
        a, b = c.src_at(t0), c.src_at(t1)
        lo, hi = (b, a) if c.reverse else (a, b)
        part.src_in, part.src_out = int(round(lo)), int(round(hi))
        if part.src_out - part.src_in < 1:
            return None
    if t0 > c.start:
        part.transition_in = None
        part.fade_in = 0
        part.audio_fade_in = 0
    if t1 < c.end:
        part.fade_out = 0
        part.audio_fade_out = 0
    if c.keyframes and t0 > c.start:
        shift = t0 - c.start
        part.keyframes = {k: [Keyframe(t=max(0, kf.t - shift), v=kf.v, ease=kf.ease) for kf in v if kf.t - shift >= -1]
                          for k, v in c.keyframes.items()}
    return part


def _merge(ranges: list[tuple[int, int]], gap: int = 0) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in sorted((min(a, b), max(a, b)) for a, b in ranges if b != a):
        if out and a <= out[-1][1] + gap:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def delete_range(p: Project, start: int, end: int, track_ids: Optional[list[str]], ripple: bool) -> int:
    if end <= start:
        return 0
    tracks = [t for t in p.tracks if (track_ids is None or t.id in track_ids) and not t.locked]
    span = end - start
    for t in tracks:
        _clear_range(t, start, end)
        if ripple:
            _shift(t, end, -span)
    if ripple and (track_ids is None or (p.main_track() and p.main_track().id in track_ids)):
        kept = []
        for m in p.markers:
            if start <= m.t < end:
                continue
            if m.t >= end:
                m.t -= span
            kept.append(m)
        p.markers = kept
    return span


def _scope_tracks(p: Project, media_id: str, scope: str) -> list[str]:
    if scope == "all":
        return [t.id for t in p.tracks if not t.locked]
    ids = [t.id for t in p.tracks if not t.locked and any(c.media == media_id for c in t.clips)]
    ids += [t.id for t in p.tracks if t.kind == "text" and not t.locked and t.id not in ids]
    return ids


def source_to_timeline(p: Project, media_id: str, ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Timeline ranges where the given source ranges of a media are shown (every clip of that media)."""
    out: list[tuple[int, int]] = []
    for _, c in p.all_clips():
        if c.media != media_id or c.type != "media":
            continue
        for a, b in ranges:
            lo, hi = max(a, c.src_in), min(b, c.src_out)
            if hi - lo <= 0:
                continue
            t0, t1 = sorted((c.timeline_at(lo), c.timeline_at(hi)))
            out.append((int(round(t0)), int(round(t1))))
    return _merge(out)


# ------------------------------------------------------------------ operations

def _add_media(ctx: Ctx, o: AddMedia) -> dict:
    p = ctx.p
    info = ctx.media(o.media)
    track = p.track(o.track) if o.track else _default_track(ctx, info)
    _unlocked(track)
    if track.kind == "text":
        raise LumiereError("Media goes on a video or audio track, not on a text track.")
    if track.kind == "video" and not (info.get("has_video") or info.get("kind") == "image"):
        raise LumiereError(f"{info.get('name')} has no picture: put it on an audio track.")
    a, b = _media_span(ctx, info, _t(o.src_in), _t(o.src_out), _t(o.length))
    clip = Clip(media=o.media, src_in=a, src_out=b, label=o.label or str(info.get("name") or "")[:120])
    if o.fit:
        clip.transform.fit = o.fit
    elif track.kind == "video":
        cw, ch = p.canvas.width, p.canvas.height
        mw, mh = int(info.get("width") or cw), int(info.get("height") or ch)
        # Same orientation: fill the frame; a horizontal video on a vertical canvas: keep it whole (reframe crops it on request).
        clip.transform.fit = "cover" if (mw >= mh) == (cw >= ch) and abs(mw / max(1, mh) - cw / ch) < 0.15 else "contain"
    at = _t(o.at)
    if at is None or o.mode == "append":
        clip.start = _track_end(track) if at is None else ctx.snap(at)
        if at is not None:
            _clear_range(track, clip.start, clip.end)
    elif o.mode == "insert":
        clip.start = ctx.snap(at)
        hit = next((c for c in track.clips if c.start < clip.start < c.end), None)
        if hit:
            _split_clip(track, hit, clip.start)
        _shift(track, clip.start, clip.duration)
    else:
        clip.start = ctx.snap(at)
        _clear_range(track, clip.start, clip.end)
    track.clips.append(clip)
    return {"clip": clip.id, "track": track.id, "start": clip.start, "end": clip.end}


def _add_text(ctx: Ctx, o: AddText) -> dict:
    p = ctx.p
    track = p.track(o.track) if o.track else next((t for t in p.tracks if t.kind == "text" and not t.locked), None)
    if track is None:
        track = Track(kind="text", name="Textos", role="titles")
        p.tracks.append(track)
    if track.kind != "text":
        raise LumiereError("Text goes on a text track.")
    _unlocked(track)
    style = TextStyle(**o.style)
    clip = Clip(type="text", text=o.text, start=ctx.snap(_t(o.start) or 0), length=max(MIN_CLIP_MS, _t(o.length) or 3000), style=style,
                transform=Transform(x=o.x, y=o.y))
    _clear_range(track, clip.start, clip.end)
    track.clips.append(clip)
    return {"clip": clip.id, "track": track.id, "start": clip.start, "end": clip.end}


def _split_clip(track: Track, c: Clip, at: int) -> Optional[str]:
    if not (c.start + MIN_CLIP_MS // 2 < at < c.end - MIN_CLIP_MS // 2):
        return None
    left = _cut_clip(c, c.start, at)
    right = _cut_clip(c, at, c.end, new_id_for_part=True)
    if not left or not right:
        return None
    idx = track.clips.index(c)
    track.clips[idx:idx + 1] = [left, right]
    return right.id


def _split(ctx: Ctx, o: Split) -> dict:
    at = ctx.snap(_t(o.at))
    created: list[str] = []
    if o.clip:
        track, c = ctx.p.find(o.clip)
        _unlocked(track)
        new = _split_clip(track, c, at)
        if not new:
            raise LumiereError(f"{at} ms is not inside clip {o.clip} (or too close to an edge).")
        created.append(new)
    else:
        for track in ctx.p.tracks:
            if track.locked:
                continue
            for c in list(track.clips):
                new = _split_clip(track, c, at)
                if new:
                    created.append(new)
    return {"at": at, "new_clips": created}


def _trim(ctx: Ctx, o: Trim) -> dict:
    track, c = ctx.p.find(o.clip)
    _unlocked(track)
    old_end = c.end
    if c.type == "text" or (c.media and ctx.media(c.media).get("kind") == "image"):
        length = _t(o.length)
        if length is None:
            raise LumiereError("Text and image clips are trimmed with 'length'.")
        if c.type == "text":
            c.length = max(MIN_CLIP_MS, length)
        else:
            c.src_out = c.src_in + int(max(MIN_CLIP_MS, length) * c.speed)
    else:
        info = ctx.media(c.media)
        dur = int(info.get("duration_ms") or 0)
        new_in = c.src_in if o.src_in is None else max(0, _t(o.src_in))
        new_out = c.src_out if o.src_out is None else _t(o.src_out)
        if dur:
            new_out = min(new_out, dur)
        if new_out - new_in < MIN_CLIP_MS:
            raise LumiereError("That trim leaves the clip empty.")
        c.src_in, c.src_out = new_in, new_out
    delta = c.end - old_end
    if o.ripple and delta:
        _shift(track, old_end, delta, exclude={c.id})
    elif delta > 0:
        _clear_range(track, old_end, c.end, keep={c.id})
    return {"clip": c.id, "start": c.start, "end": c.end, "src_in": c.src_in, "src_out": c.src_out}


def _move(ctx: Ctx, o: Move) -> dict:
    p = ctx.p
    track, c = p.find(o.clip)
    _unlocked(track)
    dest = p.track(o.track) if o.track else track
    _unlocked(dest)
    if (dest.kind == "text") != (c.type == "text"):
        raise LumiereError("Text clips stay on text tracks and media clips on video or audio tracks.")
    if dest.kind == "video" and c.media and not (ctx.media(c.media).get("has_video") or ctx.media(c.media).get("kind") == "image"):
        raise LumiereError("That media has no picture: it cannot go on a video track.")
    track.clips.remove(c)
    if o.start is not None:
        c.start = ctx.snap(max(0, _t(o.start)))
    c.transition_in = None if dest is not track else c.transition_in
    _clear_range(dest, c.start, c.end)
    dest.clips.append(c)
    return {"clip": c.id, "track": dest.id, "start": c.start, "end": c.end}


def _delete(ctx: Ctx, o: Delete) -> dict:
    removed = []
    for clip_id in o.clips:
        track, c = ctx.p.find(clip_id)
        _unlocked(track)
        track.clips.remove(c)
        removed.append(clip_id)
        if not o.ripple:
            continue
        following = sorted((x for x in track.clips if x.start >= c.start), key=lambda x: x.start)
        if not following:
            continue
        first = following[0]
        if first.start > c.end:
            continue  # a gap after the clip stays a gap
        if first.transition_in is not None and first.start < c.end:
            first.transition_in = None  # its transition was with the deleted clip
        prev_end = max((x.end for x in track.clips if x.start < c.start), default=c.start)
        target = max(c.start if prev_end <= c.start else prev_end, 0)
        _shift(track, first.start, target - first.start)
    return {"removed": removed}


def _delete_range(ctx: Ctx, o: DeleteRange) -> dict:
    a, b = ctx.snap(_t(o.start)), ctx.snap(_t(o.end))
    if b <= a:
        raise LumiereError("The range is empty (end must be after start).")
    for tid in o.tracks or []:
        ctx.p.track(tid)
    removed = delete_range(ctx.p, a, b, o.tracks, o.ripple)
    return {"removed_ms": removed, "duration": ctx.p.duration}


def _source_ranges(o_ranges: list[list[Time]]) -> list[tuple[int, int]]:
    out = []
    for r in o_ranges:
        if len(r) != 2:
            raise LumiereError("Each range is [from, to].")
        a, b = _t(r[0]), _t(r[1])
        if b > a:
            out.append((a, b))
    return out


def _cut_source(ctx: Ctx, o: CutSource) -> dict:
    ctx.media(o.media)
    ranges = _merge(_source_ranges(o.ranges), gap=o.min_gap)
    timeline = source_to_timeline(ctx.p, o.media, ranges)
    tracks = _scope_tracks(ctx.p, o.media, o.scope)
    total = 0
    for a, b in reversed(timeline):  # from the end, so earlier ranges keep their positions
        total += delete_range(ctx.p, a, b, tracks, o.ripple)
    return {"cuts": len(timeline), "removed_ms": total, "duration": ctx.p.duration}


def _keep_source(ctx: Ctx, o: KeepSource) -> dict:
    ctx.media(o.media)
    keep = _merge(_source_ranges(o.ranges))
    spans = [(c.src_in, c.src_out) for _, c in ctx.p.all_clips() if c.media == o.media]
    cut: list[tuple[int, int]] = []
    for lo, hi in spans:
        cursor = lo
        for a, b in keep:
            if b <= cursor or a >= hi:
                continue
            if a > cursor:
                cut.append((cursor, a))
            cursor = max(cursor, b)
        if cursor < hi:
            cut.append((cursor, hi))
    if not cut:
        return {"cuts": 0, "removed_ms": 0, "duration": ctx.p.duration}
    return _cut_source(ctx, CutSource(op="cut_source", media=o.media, ranges=[list(r) for r in cut], scope=o.scope))


_SETTABLE = {"label", "mute", "volume_db", "fade_in", "fade_out", "audio_fade_in", "audio_fade_out", "transform", "crop", "text", "style", "color",
             "speed", "reverse", "audio_stream", "keyframes", "filters", "reframe", "transition_in", "start", "src_in", "src_out", "length"}
_MERGED = {"transform": Transform, "crop": Crop, "style": TextStyle}


def _set(ctx: Ctx, o: SetClip) -> dict:
    track, c = ctx.p.find(o.clip)
    _unlocked(track)
    unknown = set(o.props) - _SETTABLE
    if unknown:
        raise LumiereError(f"Not settable: {', '.join(sorted(unknown))}. Settable: {', '.join(sorted(_SETTABLE))}.")
    old_end = c.end
    data = c.model_dump()
    for key, value in o.props.items():
        if key in _MERGED and isinstance(value, dict):
            base = data.get(key) or _MERGED[key]().model_dump()
            data[key] = {**base, **value}
        elif key in ("start", "src_in", "src_out", "length") and value is not None:
            data[key] = _t(value)
        else:
            data[key] = value
    try:
        new = Clip.model_validate(data)
    except ValidationError as error:
        issues = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'clip'}: {e['msg']}" for e in error.errors())
        raise LumiereError(issues) from error
    track.clips[track.clips.index(c)] = new
    delta = new.end - old_end
    if delta and o.ripple and "start" not in o.props:
        _shift(track, old_end, delta, exclude={new.id})
    return {"clip": new.id, "start": new.start, "end": new.end}


def _speed(ctx: Ctx, o: Speed) -> dict:
    return _set(ctx, SetClip(op="set", clip=o.clip, props={"speed": o.speed}, ripple=o.ripple))


def _transition(ctx: Ctx, o: TransitionOp) -> dict:
    p = ctx.p
    targets: list[tuple[Track, Clip]] = []
    if o.all_cuts:
        track = p.track(o.track) if o.track else p.main_track()
        if track is None:
            raise LumiereError("No video track.")
        track.clips.sort(key=lambda c: c.start)
        targets = [(track, c) for c in track.clips[1:]]
    elif o.clip:
        targets = [p.find(o.clip)]
    else:
        raise LumiereError("Give 'clip' or all_cuts=true.")
    done = []
    for track, c in targets:
        _unlocked(track)
        track.clips.sort(key=lambda x: x.start)
        idx = track.clips.index(c)
        prev = track.clips[idx - 1] if idx > 0 else None
        had = c.transition_in.dur if c.transition_in else 0
        if o.type is None:
            if had and prev and prev.end > c.start:
                c.transition_in = None
                _shift(track, c.start, had)
            else:
                c.transition_in = None
            done.append(c.id)
            continue
        dur = o.dur
        if prev is None:
            # first clip: a fade from black instead of a transition
            c.fade_in = dur
            done.append(c.id)
            continue
        dur = min(dur, prev.duration - MIN_CLIP_MS, c.duration - MIN_CLIP_MS)
        if dur < MIN_CLIP_MS:
            continue
        gap = c.start - prev.end
        if had:
            # already overlapping: adjust to the new length
            _shift(track, c.start, had - dur)
        elif gap <= 1000 / p.canvas.fps + 1:
            _shift(track, c.start, -(dur + max(0, gap)))
        else:
            continue  # a real gap: no transition across it
        c.transition_in = Transition(type=o.type, dur=dur)
        done.append(c.id)
    return {"clips": done}


def _filter_add(ctx: Ctx, o: FilterAdd) -> dict:
    p = ctx.p
    clips: list[Clip] = []
    if o.clips:
        clips = [p.find(cid)[1] for cid in o.clips]
    elif o.track:
        clips = [c for c in p.track(o.track).clips if c.type == "media"]
    else:
        main = p.main_track()
        clips = [c for c in (main.clips if main else []) if c.type == "media"]
    from .render.filters import check_params  # lazy: render imports ops

    params = check_params(o.type, o.params)
    for c in clips:
        c.filters = [f for f in c.filters if f.type != o.type] + [Filter(type=o.type, params=params)]
    return {"clips": [c.id for c in clips], "filter": o.type}


def _filter_remove(ctx: Ctx, o: FilterRemove) -> dict:
    _, c = ctx.p.find(o.clip)
    before = len(c.filters)
    if o.index is not None:
        if not 0 <= o.index < before:
            raise LumiereError("No filter at that index.")
        c.filters.pop(o.index)
    elif o.type:
        c.filters = [f for f in c.filters if f.type != o.type]
    else:
        c.filters = []
    return {"clip": c.id, "removed": before - len(c.filters)}


def _track_add(ctx: Ctx, o: TrackAdd) -> dict:
    p = ctx.p
    if len(p.tracks) >= 24:
        raise LumiereError("24 tracks at most.")
    role = o.role or {"video": "overlay", "audio": "sfx", "text": "titles"}[o.kind]
    if role == "main" and p.main_track() and p.main_track().role == "main":
        raise LumiereError("There is already a main track.")
    t = Track(kind=o.kind, name=o.name or {"video": "Vídeo", "audio": "Audio", "text": "Textos"}[o.kind], role=role)
    if o.id:
        t.id = o.id
    p.tracks.insert(o.index if o.index is not None else len(p.tracks), t)
    return {"track": t.id}


def _track_set(ctx: Ctx, o: TrackSet) -> dict:
    t = ctx.p.track(o.track)
    allowed = {"name", "muted", "hidden", "locked", "volume_db", "role", "duck"}
    unknown = set(o.props) - allowed
    if unknown:
        raise LumiereError(f"Not settable on a track: {', '.join(sorted(unknown))}.")
    data = {**t.model_dump(), **o.props}
    new = Track.model_validate(data)
    ctx.p.tracks[ctx.p.tracks.index(t)] = new
    return {"track": new.id}


def _track_delete(ctx: Ctx, o: TrackDelete) -> dict:
    t = ctx.p.track(o.track)
    ctx.p.tracks.remove(t)
    return {"track": t.id, "removed_clips": len(t.clips)}


def _canvas(ctx: Ctx, o: CanvasOp) -> dict:
    data = ctx.p.canvas.model_dump()
    if o.preset:
        preset = PRESETS.get(o.preset)
        if not preset:
            raise LumiereError(f"Unknown preset {o.preset!r}. Known: {', '.join(PRESETS)}.")
        data.update({k: preset[k] for k in ("width", "height", "fps")})
    for key in ("width", "height", "fps", "background"):
        value = getattr(o, key)
        if value is not None:
            data[key] = value
    ctx.p.canvas = Canvas.model_validate(data)
    if o.length_mode:
        ctx.p.length_mode = o.length_mode
    if o.fit:
        for t in ctx.p.tracks:
            if t.kind == "video":
                for c in t.clips:
                    c.transform.fit = o.fit
    return {"canvas": ctx.p.canvas.model_dump(), "length_mode": ctx.p.length_mode}


def _marker_add(ctx: Ctx, o: MarkerAdd) -> dict:
    m = Marker(t=ctx.snap(_t(o.t)), label=o.label, color=o.color, kind=o.kind)
    ctx.p.markers.append(m)
    ctx.p.markers.sort(key=lambda m: m.t)
    return {"marker": m.id, "t": m.t}


def _marker_delete(ctx: Ctx, o: MarkerDelete) -> dict:
    before = len(ctx.p.markers)
    ctx.p.markers = [m for m in ctx.p.markers if not ((o.id and m.id == o.id) or (o.kind and m.kind == o.kind))]
    return {"removed": before - len(ctx.p.markers)}


def _captions(ctx: Ctx, o: CaptionsOp) -> dict:
    data = {**ctx.p.captions.model_dump(), **o.props}
    if o.enabled is not None:
        data["enabled"] = o.enabled
    if o.style is not None:
        data["style"] = o.style
    ctx.p.captions = Captions.model_validate(data)
    return {"captions": ctx.p.captions.model_dump()}


def _duplicate(ctx: Ctx, o: Duplicate) -> dict:
    track, c = ctx.p.find(o.clip)
    _unlocked(track)
    copy_ = c.model_copy(deep=True)
    copy_.id = new_id("clp")
    copy_.transition_in = None
    at = _t(o.at)
    copy_.start = c.end if at is None else ctx.snap(at)
    _shift(track, copy_.start, copy_.duration)
    track.clips.append(copy_)
    return {"clip": copy_.id, "start": copy_.start, "end": copy_.end}


def _detach_audio(ctx: Ctx, o: DetachAudio) -> dict:
    p = ctx.p
    track, c = p.find(o.clip)
    if c.type != "media" or track.kind != "video":
        raise LumiereError("Only media clips on a video track have audio to detach.")
    if not ctx.media(c.media).get("has_audio"):
        raise LumiereError("That media has no sound.")
    dest = p.track(o.track) if o.track else next((t for t in p.tracks if t.kind == "audio" and t.role == "voice" and not t.locked), None)
    if dest is None:
        dest = Track(kind="audio", name="Voz", role="voice")
        p.tracks.append(dest)
    audio = Clip(media=c.media, src_in=c.src_in, src_out=c.src_out, start=c.start, speed=c.speed, reverse=c.reverse, volume_db=c.volume_db,
                 audio_fade_in=c.audio_fade_in, audio_fade_out=c.audio_fade_out, audio_stream=c.audio_stream, label=c.label,
                 filters=[f for f in c.filters if f.type in _AUDIO_FILTER_TYPES])
    _clear_range(dest, audio.start, audio.end)
    dest.clips.append(audio)
    c.mute = True
    return {"clip": audio.id, "track": dest.id}


_AUDIO_FILTER_TYPES = {"audio_denoise", "voice_enhance", "highpass", "lowpass", "compressor", "pitch", "echo"}


def _close_gaps(ctx: Ctx, o: CloseGaps) -> dict:
    tracks = [ctx.p.track(o.track)] if o.track else [t for t in ctx.p.tracks if not t.locked]
    closed = 0
    for t in tracks:
        t.clips.sort(key=lambda c: c.start)
        cursor = 0
        for c in t.clips:
            target = cursor - (c.transition_in.dur if c.transition_in and cursor else 0)
            if c.start > target:
                closed += c.start - target
                c.start = max(0, target)
            cursor = max(cursor, c.end)
    return {"closed_ms": closed}


def _replace_media(ctx: Ctx, o: ReplaceMedia) -> dict:
    track, c = ctx.p.find(o.clip)
    info = ctx.media(o.media)
    if c.type != "media":
        raise LumiereError("Only media clips can change their media.")
    span = c.src_out - c.src_in
    dur = int(info.get("duration_ms") or 0)
    c.media = o.media
    if info.get("kind") == "image":
        c.src_in, c.src_out = 0, span
    else:
        c.src_in = min(c.src_in, max(0, dur - span)) if dur else c.src_in
        c.src_out = min(c.src_in + span, dur) if dur else c.src_in + span
    c.reframe = None
    c.label = str(info.get("name") or c.label)[:120]
    return {"clip": c.id, "src_in": c.src_in, "src_out": c.src_out}


def _sequence(ctx: Ctx, o: Sequence) -> dict:
    created = []
    for item in o.items:
        r = _add_media(ctx, AddMedia(op="add_media", media=item["media"], track=o.track, src_in=item.get("src_in"), src_out=item.get("src_out"),
                                     length=item.get("length"), label=item.get("label", "")))
        created.append(r["clip"])
        if not o.track:
            o.track = r["track"]
    return {"clips": created, "track": o.track}


def _keyframes(ctx: Ctx, o: KeyframesOp) -> dict:
    track, c = ctx.p.find(o.clip)
    _unlocked(track)
    keys = sorted(o.keys, key=lambda k: k.t)
    if keys:
        c.keyframes[o.prop] = keys
    else:
        c.keyframes.pop(o.prop, None)
    return {"clip": c.id, "prop": o.prop, "keys": len(keys)}


def _notes(ctx: Ctx, o: Notes) -> dict:
    ctx.p.notes = o.text
    return {"ok": True}


HANDLERS: dict[str, Callable[[Ctx, Any], dict]] = {
    "add_media": _add_media, "add_text": _add_text, "split": _split, "trim": _trim, "move": _move, "delete": _delete,
    "delete_range": _delete_range, "cut_source": _cut_source, "keep_source": _keep_source, "set": _set, "speed": _speed,
    "transition": _transition, "filter_add": _filter_add, "filter_remove": _filter_remove, "track_add": _track_add, "track_set": _track_set,
    "track_delete": _track_delete, "canvas": _canvas, "marker_add": _marker_add, "marker_delete": _marker_delete, "captions": _captions,
    "duplicate": _duplicate, "detach_audio": _detach_audio, "close_gaps": _close_gaps, "replace_media": _replace_media,
    "sequence": _sequence, "keyframes": _keyframes, "notes": _notes,
}


def apply_ops(project: Project, ops: list[dict[str, Any]], media: MediaLookup) -> tuple[Project, list[dict[str, Any]]]:
    """Apply ``ops`` in order to a copy of ``project``. All or nothing: the first failure raises and the original is untouched."""
    work = clone(project)
    ctx = Ctx(work, media)
    results: list[dict[str, Any]] = []
    for index, raw in enumerate(ops):
        op = parse_op(raw)
        try:
            result = HANDLERS[op.op](ctx, op)
        except (LumiereError, NotFound) as error:
            prefix = f"Step {index + 1} ({op.op}): " if len(ops) > 1 else ""
            raise type(error)(prefix + str(error)) from error
        work.sort()
        results.append({"op": op.op, **result})
    try:
        final = Project.model_validate(work.dump())
    except ValidationError as error:
        issues = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors()[:5])
        raise LumiereError(f"The result is not a valid project: {issues}") from error
    return final, results
