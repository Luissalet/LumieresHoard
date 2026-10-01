"""The project document: canvas, tracks, clips, markers and captions. Times are integer milliseconds.

A media clip shows ``[src_in, src_out)`` of its media from ``start`` on the timeline; its length on the timeline is
``(src_out - src_in) / speed``. A media clip on a video track carries its own audio (muted with ``mute``); audio
tracks hold sound only. Text clips have ``start`` and ``length``. Clips on one track never overlap, except a clip
with ``transition_in`` which overlaps the previous one by at most the transition length.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import LumiereError, NotFound
from .util import new_id

SCHEMA = "lumiere/1"
MIN_CLIP_MS = 40
MAX_TRACKS = 24
MAX_CLIPS = 4000

TrackKind = Literal["video", "audio", "text"]
FitMode = Literal["contain", "cover", "fill", "none"]
TransitionType = Literal["crossfade", "dissolve", "fade_black", "fade_white", "slide_left", "slide_right", "slide_up", "slide_down",
                         "wipe_left", "wipe_right", "wipe_up", "wipe_down", "circle_open", "circle_close", "zoom_in", "pixelize",
                         "radial", "smooth_left", "smooth_right", "blur"]
FilterType = Literal["eq", "lut", "grayscale", "sepia", "vignette", "blur", "sharpen", "denoise", "hflip", "vflip",
                     "chromakey", "vintage", "warm", "cool", "contrast_pop", "pixelate",
                     "audio_denoise", "voice_enhance", "highpass", "lowpass", "compressor", "pitch", "echo"]
CaptionStyle = Literal["clean", "bold", "karaoke", "pop", "boxed", "minimal"]
Ease = Literal["linear", "hold", "ease_in", "ease_out", "ease_in_out"]
KeyProp = Literal["x", "y", "scale", "opacity", "rotation", "volume_db"]

TRANSITIONS = TransitionType.__args__  # type: ignore[attr-defined]
FILTERS = FilterType.__args__  # type: ignore[attr-defined]
AUDIO_FILTERS = {"audio_denoise", "voice_enhance", "highpass", "lowpass", "compressor", "pitch", "echo"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=False)


class Canvas(Strict):
    width: int = Field(1920, ge=64, le=7680)
    height: int = Field(1080, ge=64, le=7680)
    fps: float = Field(30.0, ge=1, le=240)
    background: str = Field("#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    sample_rate: int = Field(48000, ge=8000, le=192000)

    @field_validator("width", "height")
    @classmethod
    def _even(cls, v: int) -> int:
        return v - (v % 2)


class Transform(Strict):
    x: float = Field(0.0, ge=-2, le=2, description="Horizontal offset as a fraction of the canvas width (0 = centred).")
    y: float = Field(0.0, ge=-2, le=2)
    scale: float = Field(1.0, gt=0, le=20)
    rotation: float = Field(0.0, ge=-360, le=360)
    opacity: float = Field(1.0, ge=0, le=1)
    fit: FitMode = "contain"
    focus_x: float = Field(0.5, ge=0, le=1, description="With fit=cover: which part of the frame stays visible (0 left, 1 right).")
    focus_y: float = Field(0.5, ge=0, le=1)


class Crop(Strict):
    left: float = Field(0.0, ge=0, le=0.45)
    top: float = Field(0.0, ge=0, le=0.45)
    right: float = Field(0.0, ge=0, le=0.45)
    bottom: float = Field(0.0, ge=0, le=0.45)


class Filter(Strict):
    type: FilterType
    params: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class Transition(Strict):
    type: TransitionType = "crossfade"
    dur: int = Field(500, ge=40, le=5000)


class Keyframe(Strict):
    t: int = Field(..., ge=0, description="ms from the clip's start on the timeline.")
    v: float
    ease: Ease = "linear"


class Reframe(Strict):
    """A focus path computed by the auto-reframe tool: [[src_ms, focus_x, focus_y], ...]."""

    path: list[list[float]] = Field(default_factory=list, max_length=20000)
    mode: Literal["track", "stable", "center"] = "track"


class TextStyle(Strict):
    font: str = Field("Arial", max_length=80)
    size: int = Field(72, ge=8, le=600, description="Pixels at the canvas size.")
    color: str = Field("#FFFFFF", pattern=r"^#[0-9a-fA-F]{6}$")
    outline: str = Field("#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    outline_width: float = Field(4, ge=0, le=40)
    box: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$", description="Background box colour (#RRGGBB or #RRGGBBAA).")
    bold: bool = True
    italic: bool = False
    align: Literal["left", "center", "right"] = "center"
    position: Literal["top", "middle", "bottom"] = "middle"
    margin: int = Field(80, ge=0, le=2000)
    animation: Literal["none", "fade", "pop", "slide_up", "typewriter"] = "fade"
    shadow: float = Field(2, ge=0, le=20)


class Clip(Strict):
    id: str = Field(default_factory=lambda: new_id("clp"))
    type: Literal["media", "text"] = "media"
    start: int = Field(0, ge=0)
    # media clips
    media: Optional[str] = None
    src_in: int = Field(0, ge=0)
    src_out: int = Field(0, ge=0)
    speed: float = Field(1.0, ge=0.1, le=16)
    reverse: bool = False
    audio_stream: int = Field(0, ge=0, le=16)
    # text clips
    length: int = Field(0, ge=0, description="Length of a text clip (ms).")
    text: str = Field("", max_length=4000)
    style: Optional[TextStyle] = None
    # shared
    label: str = Field("", max_length=120)
    mute: bool = False
    volume_db: float = Field(0.0, ge=-60, le=24)
    fade_in: int = Field(0, ge=0, le=60000, description="Video opacity fade-in (ms).")
    fade_out: int = Field(0, ge=0, le=60000)
    audio_fade_in: int = Field(0, ge=0, le=60000)
    audio_fade_out: int = Field(0, ge=0, le=60000)
    transform: Transform = Field(default_factory=Transform)
    crop: Crop = Field(default_factory=Crop)
    filters: list[Filter] = Field(default_factory=list, max_length=24)
    transition_in: Optional[Transition] = None
    keyframes: dict[KeyProp, list[Keyframe]] = Field(default_factory=dict)
    reframe: Optional[Reframe] = None
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")

    @property
    def duration(self) -> int:
        if self.type == "text":
            return self.length
        return int(round((self.src_out - self.src_in) / self.speed))

    @property
    def end(self) -> int:
        return self.start + self.duration

    def src_at(self, t: int) -> float:
        """Source time (ms) shown at timeline time ``t``."""
        offset = (t - self.start) * self.speed
        return (self.src_out - offset) if self.reverse else (self.src_in + offset)

    def timeline_at(self, src: float) -> float:
        return self.start + ((self.src_out - src) if self.reverse else (src - self.src_in)) / self.speed

    @model_validator(mode="after")
    def _check(self) -> "Clip":
        if self.type == "media":
            if not self.media:
                raise ValueError("A media clip needs a media id.")
            if self.src_out - self.src_in < MIN_CLIP_MS * self.speed * 0.5:
                raise ValueError(f"Clip {self.id} is too short (src_in {self.src_in}, src_out {self.src_out}).")
        else:
            if self.length < MIN_CLIP_MS:
                raise ValueError(f"Text clip {self.id} needs a length of at least {MIN_CLIP_MS} ms.")
        return self


class Track(Strict):
    id: str = Field(default_factory=lambda: new_id("trk"))
    kind: TrackKind = "video"
    name: str = Field("", max_length=60)
    muted: bool = False
    hidden: bool = False
    locked: bool = False
    volume_db: float = Field(0.0, ge=-60, le=24)
    role: Literal["main", "overlay", "voice", "music", "sfx", "titles"] = "overlay"
    duck: bool = Field(False, description="Audio tracks: lower this track while there is speech on the main / voice tracks.")
    clips: list[Clip] = Field(default_factory=list)


class Marker(Strict):
    id: str = Field(default_factory=lambda: new_id("mk"))
    t: int = Field(..., ge=0)
    label: str = Field("", max_length=120)
    color: str = Field("#F5B700", pattern=r"^#[0-9a-fA-F]{6}$")
    kind: Literal["note", "beat", "scene", "highlight", "chapter"] = "note"


class Captions(Strict):
    enabled: bool = False
    style: CaptionStyle = "bold"
    font: str = Field("Arial", max_length=80)
    size: int = Field(0, ge=0, le=400, description="0 = automatic from the canvas height.")
    color: str = Field("#FFFFFF", pattern=r"^#[0-9a-fA-F]{6}$")
    highlight: str = Field("#FFD400", pattern=r"^#[0-9a-fA-F]{6}$")
    outline: str = Field("#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    position: Literal["top", "middle", "bottom", "lower_third"] = "lower_third"
    max_words: int = Field(4, ge=1, le=16)
    max_chars: int = Field(32, ge=8, le=120)
    uppercase: bool = False
    tracks: list[str] = Field(default_factory=list, description="Track ids whose speech is captioned; empty = the main track.")


class Project(Strict):
    schema_: str = Field(SCHEMA, alias="schema")
    canvas: Canvas = Field(default_factory=Canvas)
    tracks: list[Track] = Field(default_factory=list, max_length=MAX_TRACKS)
    markers: list[Marker] = Field(default_factory=list, max_length=5000)
    captions: Captions = Field(default_factory=Captions)
    notes: str = Field("", max_length=8000)
    length_mode: Literal["main", "longest"] = Field("main", description="main: the video ends with the main track (music or titles past it are cut); longest: with the last clip of any track.")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # ------------------------------------------------------------ lookup
    def track(self, track_id: str) -> Track:
        for t in self.tracks:
            if t.id == track_id:
                return t
        raise NotFound(f"No track {track_id} in this project.")

    def find(self, clip_id: str) -> tuple[Track, Clip]:
        for t in self.tracks:
            for c in t.clips:
                if c.id == clip_id:
                    return t, c
        raise NotFound(f"No clip {clip_id} in this project.")

    def main_track(self) -> Optional[Track]:
        for t in self.tracks:
            if t.kind == "video" and t.role == "main":
                return t
        return next((t for t in self.tracks if t.kind == "video"), None)

    @property
    def duration(self) -> int:
        main = self.main_track()
        if self.length_mode == "main" and main is not None and main.clips:
            return max(c.end for c in main.clips)
        return max((c.end for t in self.tracks for c in t.clips), default=0)

    @property
    def content_end(self) -> int:
        return max((c.end for t in self.tracks for c in t.clips), default=0)

    def all_clips(self):
        for t in self.tracks:
            for c in t.clips:
                yield t, c

    def media_ids(self) -> set[str]:
        return {c.media for _, c in self.all_clips() if c.media}

    def sort(self) -> None:
        for t in self.tracks:
            t.clips.sort(key=lambda c: (c.start, c.id))

    def dump(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=False)


def new_project(width: int = 1920, height: int = 1080, fps: float = 30.0) -> Project:
    return Project(canvas=Canvas(width=width, height=height, fps=fps), tracks=[
        Track(kind="video", name="Principal", role="main"),
        Track(kind="text", name="Textos", role="titles"),
        Track(kind="audio", name="Música", role="music", duck=True),
    ])


def load(doc: dict[str, Any]) -> Project:
    return Project.model_validate(doc)


def validate(project: Project, media_lookup=None) -> list[dict[str, Any]]:
    """Problems that would make the render wrong: overlaps, clips past the end of their media, unknown media.
    Returns a list of {level, code, message, clip?, track?} (empty when everything is fine)."""
    issues: list[dict[str, Any]] = []
    ids: set[str] = set()
    total = 0
    for t in project.tracks:
        prev: Optional[Clip] = None
        for c in sorted(t.clips, key=lambda c: c.start):
            total += 1
            if c.id in ids:
                issues.append({"level": "error", "code": "duplicate_id", "message": f"Duplicated clip id {c.id}.", "clip": c.id})
            ids.add(c.id)
            if t.kind == "text" and c.type != "text":
                issues.append({"level": "error", "code": "wrong_track", "message": f"Clip {c.id} is media on a text track.", "clip": c.id})
            if t.kind != "text" and c.type == "text":
                issues.append({"level": "error", "code": "wrong_track", "message": f"Text clip {c.id} is on a {t.kind} track.", "clip": c.id})
            if prev is not None and c.start < prev.end:
                overlap = prev.end - c.start
                allowed = c.transition_in.dur if c.transition_in else 0
                if overlap > allowed + 1:
                    issues.append({"level": "error", "code": "overlap", "track": t.id, "clip": c.id,
                                   "message": f"Clip {c.id} overlaps {prev.id} by {overlap} ms on track {t.name or t.id}."})
            if c.type == "media" and media_lookup is not None:
                info = media_lookup(c.media)
                if info is None:
                    issues.append({"level": "error", "code": "missing_media", "clip": c.id, "message": f"Clip {c.id} uses unknown media {c.media}."})
                else:
                    if info.get("missing"):
                        issues.append({"level": "error", "code": "file_missing", "clip": c.id, "message": f"The file of {info.get('name')} is missing: {info.get('path')}."})
                    dur = int(info.get("duration_ms") or 0)
                    if info.get("kind") != "image" and dur and c.src_out > dur + 50:
                        issues.append({"level": "warning", "code": "past_end", "clip": c.id,
                                       "message": f"Clip {c.id} asks for {c.src_out} ms of a {dur} ms media; the rest will be frozen or silent."})
                    if t.kind == "audio" and not info.get("has_audio"):
                        issues.append({"level": "warning", "code": "no_audio", "clip": c.id, "message": f"Clip {c.id} is on an audio track but its media has no sound."})
                    if c.reverse and c.src_out - c.src_in > 60000:
                        issues.append({"level": "error", "code": "reverse_too_long", "clip": c.id, "message": "Reverse playback is limited to 60 s of source per clip."})
            prev = c if prev is None or c.end > prev.end else prev
    if total > MAX_CLIPS:
        issues.append({"level": "error", "code": "too_many_clips", "message": f"{total} clips: the limit is {MAX_CLIPS}."})
    return issues


def clone(project: Project) -> Project:
    return Project.model_validate(copy.deepcopy(project.dump()))


def snap(ms: float, fps: float) -> int:
    """Round to the frame grid of the canvas."""
    frame = 1000.0 / fps
    return int(round(round(ms / frame) * frame))


def frames(ms: int, fps: float) -> int:
    return int(math.floor(ms * fps / 1000 + 1e-6))


def require(cond: bool, message: str, code: str | None = None) -> None:
    if not cond:
        raise LumiereError(message, code=code)
