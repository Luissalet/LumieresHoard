"""Tools exposed to assistants. One catalogue drives /api/agent/*, mcp_server.py and part of the UI routes."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, Field

from . import analyze, commands, derive
from . import broll as broll_mod
from . import music as music_mod
from . import media as media_store
from . import plan as plan_mod
from . import projects as project_store
from .errors import LumiereError
from .ops import OP_NAMES, PRESETS, op_reference
from .render import filters as fx
from .render import runner
from .services import Services
from .timeline import TRANSITIONS
from .util import ms_to_tc, parse_time

AGENT_INSTRUCTIONS = """Lumiere's Hoard edits videos on this computer. Typical flow: media_import (a file or folder the user names; nothing is
copied) -> project_create (preset: reels, youtube, square...; media to start with) -> look with project_get (outline) and frame_snapshot ->
edit -> render_start -> job_status until done -> tell the user the file path.
Two ways to edit: (1) plan_create with the user's words ("quita los silencios, subtítulos y vertical"), show the steps, then plan_apply;
(2) precise work: timeline_edit with operations (ids come from project_get), or edit_command for smart edits (remove_silences,
remove_fillers, cut_words, split_scenes, reframe, captions, beat_sync, match_loudness). Times are ms or '1:23.5'.
Text-based editing: timeline_transcript shows the words heard on the timeline with ids; text_cut removes words or keeps only some.
Smart edits and captions need analyses (transcript, scenes, focus, beats, loudness): when one is missing the tool queues it and says so;
check job_status and repeat. Background music: music_pick ranks a folder's tracks for the edit (add='best' places it); b-roll: broll_suggest
matches library clips to what is said (place='best', or timeline_edit add_overlay); reusable edits: template_save, template_list and
project_create with template + slots. Every change is one undo step (timeline_history undo/redo). Deletes need confirm=true and only when the
user asks. Never import or export outside the folders the user mentions. Renders run in the background; one at a time."""


class Empty(BaseModel):
    pass


ProjectId = Field(..., min_length=1, max_length=40, description="Project id (prj_...).")
MediaId = Field(..., min_length=1, max_length=40, description="Media id (med_...).")
TimeVal = Optional[float | int | str]


class MediaImportArgs(BaseModel):
    path: str = Field("", max_length=2000, description="A video, audio or image file the user named.")
    folder: str = Field("", max_length=2000, description="Or a folder: imports every media file in it.")
    recursive: bool = False


class MediaListArgs(BaseModel):
    kind: Optional[Literal["video", "audio", "image"]] = None
    query: str = Field("", max_length=200)
    limit: int = Field(100, ge=1, le=500)


class MediaRef(BaseModel):
    media: str = MediaId


class MediaDeleteArgs(MediaRef):
    confirm: bool = Field(False, description="Required. Removes it from the library (the original file stays, except uploads).")
    force: bool = Field(False, description="Also when projects use it (their clips will show as missing).")


class AnalyzeArgs(MediaRef):
    kinds: list[Literal["scenes", "beats", "loudness", "motion", "focus", "transcript"]] = Field(..., min_length=1)
    force: bool = False
    language: str = Field("", max_length=10, description="Transcript language (es, en...); empty = detect.")
    model: str = Field("", max_length=80, description="Whisper model; empty = the setting (large-v3-turbo on GPU).")


class SilencesArgs(MediaRef):
    threshold_db: Optional[float] = Field(None, ge=-80, le=0, description="Empty = automatic from the noise floor.")
    min_silence_ms: int = Field(500, ge=100, le=10000)
    margin_ms: int = Field(150, ge=0, le=2000)


class TranscriptArgs(MediaRef):
    offset: int = Field(0, ge=0)
    limit: int = Field(400, ge=1, le=3000)
    format: Literal["words", "text"] = "text"


class TranscriptFixArgs(MediaRef):
    changes: list[dict[str, str]] = Field(..., min_length=1, max_length=500, description="[{id: 'w12', text: 'corrected'}]")


class HighlightsArgs(MediaRef):
    count: int = Field(5, ge=1, le=30)
    length_s: float = Field(30, ge=3, le=600)
    mode: Literal["signals", "model"] = Field("signals", description="signals: sound, motion, cuts, speech. model: also read the transcript with the local model "
                                              "for moments that stand on their own (hook, punchline, complete thought), merged into one ranked list; "
                                              "falls back to signals when there is no transcript or model (the answer says why).")


class MediaTagArgs(MediaRef):
    tags: list[str] = Field(..., max_length=30, description="Labels for the media (replaces the old ones); b-roll suggestions match them.")


class ProjectCreateArgs(BaseModel):
    name: str = Field("Proyecto", max_length=120)
    preset: Optional[str] = Field(None, description="Canvas: " + ", ".join(PRESETS))
    media: list[str] = Field(default_factory=list, max_length=200, description="Media ids to put on the timeline in order.")
    from_project: Optional[str] = Field(None, description="Start as a copy of this project.")
    template: str = Field("", max_length=120, description="A template (id or name, see template_list): the new project keeps its titles, captions, music and "
                          "effects and replaces the media of its slots with `slots`.")
    slots: dict[str, Any] = Field(default_factory=dict, description="With template: {slot name: media id or name}, e.g. {'intro': 'logo.mp4', 'main': 'take3'}. "
                                  "A slot named main* takes its media's full length and the rest moves; slots left out keep the template's sample media.")


class TemplateSaveArgs(BaseModel):
    project: str = ProjectId
    name: str = Field(..., min_length=1, max_length=120)
    slots: dict[str, str] = Field(default_factory=dict, description="{clip id: slot name} (intro, main, outro...) on top of slots the clips already have.")


class MusicPickArgs(BaseModel):
    project: str = ProjectId
    folder: str = Field(..., max_length=2000, description="A folder with audio files (inside the folders the user named).")
    recursive: bool = False
    count: int = Field(5, ge=1, le=20)
    add: str = Field("", max_length=2000, description="'best' or the path of one suggested track: also put it under the edit (trimmed and faded to length, "
                     "ducking on) as one undo step.")
    volume_db: float = Field(-8.0, ge=-40, le=6)


class BrollArgs(BaseModel):
    project: str = ProjectId
    start: TimeVal = Field(None, description="Look for pictures for this range of the edit as a whole (ms or '1:23.5')...")
    end: TimeVal = Field(None, description="...to this time; both omitted = one query per sentence of the main track's speech.")
    per_sentence: int = Field(3, ge=1, le=8)
    use_model: bool = Field(False, description="Also ask the local model for what could be shown while each sentence is said.")
    place: Literal["none", "best"] = Field("none", description="best: put the best option of every suggestion over its sentence (muted overlays, fit cover), "
                                           "one undo step. Or place one yourself: timeline_edit add_overlay {media, start, length, src_in}.")


class ProjectGetArgs(BaseModel):
    project: str = ProjectId
    detail: Literal["outline", "full"] = Field("outline", description="outline: compact tracks/clips; full: the whole document (large).")
    track: str = Field("", max_length=40, description="Only this track (id, or kind: video|audio|text).")
    start: TimeVal = Field(None, description="Only clips that overlap from this time...")
    end: TimeVal = Field(None, description="...to this time (ms or '1:23.5').")
    max_clips: int = Field(40, ge=1, le=2000, description="Per track; longer tracks say how many clips were left out.")


class ProjectDeleteArgs(BaseModel):
    project: str = ProjectId
    confirm: bool = Field(False, description="Required. Deletes the project and its history (media and renders stay).")


class EditArgs(BaseModel):
    project: str = ProjectId
    ops: list[dict[str, Any]] = Field(..., min_length=1, max_length=500, description="Operations {op: ..., ...}: " + ", ".join(OP_NAMES) + ". Title over the start: {op: 'add_text', text, start: 0, "
                                  "length: 3000, style: {size, color, position: top|middle|bottom, animation: fade|pop|slide_up|typewriter}}. "
                                  "A wrong op or field returns every operation with its fields.")
    label: str = Field("", max_length=120, description="Name of the undo step.")
    base_rev: Optional[int] = Field(None, description="Fail if the project changed since this revision.")


class HistoryArgs(BaseModel):
    project: str = ProjectId
    action: Literal["list", "undo", "redo", "restore"] = "list"
    seq: Optional[int] = Field(None, description="restore: the history step to go back to.")


class CommandArgs(BaseModel):
    project: str = ProjectId
    command: Literal["remove_silences", "remove_fillers", "cut_words", "split_scenes", "reframe", "captions", "beat_sync", "match_loudness",
                     "script_assemble", "zoom_cuts", "music_add"]
    args: dict[str, Any] = Field(default_factory=dict, description="See the command list in plan docs / presets_list.")
    preview: bool = Field(False, description="Report what would change without saving.")


class TimelineTranscriptArgs(BaseModel):
    project: str = ProjectId
    track: Optional[str] = None
    offset: int = Field(0, ge=0)
    limit: int = Field(600, ge=1, le=4000)


class TextCutArgs(BaseModel):
    project: str = ProjectId
    media: str = MediaId
    word_ids: list[str] = Field(default_factory=list, max_length=5000)
    phrase: str = Field("", max_length=500, description="Exact phrase to cut (every occurrence).")
    keep: bool = Field(False, description="true: keep ONLY these words (cut everything else of that media).")


class PlanCreateArgs(BaseModel):
    project: str = ProjectId
    instruction: str = Field(..., min_length=2, max_length=4000)
    use_model: bool = True


class PlanApplyArgs(BaseModel):
    plan: str = Field(..., min_length=1, max_length=40)
    steps: Optional[list[dict[str, Any]]] = Field(None, description="Edited steps (same shape as plan_create returned); omit to apply as is.")
    wait_s: float = Field(1800, ge=0, le=7200, description="How long the plan may wait for analyses it needs.")


class RenderArgs(BaseModel):
    project: str = ProjectId
    preset: str = Field("final", description="Export preset: " + ", ".join(runner.EXPORTS))
    start: TimeVal = None
    end: TimeVal = None
    filename: str = Field("", max_length=120)
    folder: str = Field("", max_length=2000, description="Output folder the user named; empty = the app's renders folder.")
    lufs: Optional[float] = Field(-999, description="Loudness target (-14 social/YouTube, -16 podcast); null = untouched; omit = preset.")
    subtitles: bool = Field(False, description="Also write an .srt next to the video.")
    mode: Literal["render", "copy"] = Field("render", description="copy: lossless cut at keyframes (one source, no effects).")


class JobArgs(BaseModel):
    job: Optional[str] = Field(None, description="Job id; omit to list the active jobs.")


class JobCancelArgs(BaseModel):
    job: str


class RendersArgs(BaseModel):
    project: Optional[str] = None


class FrameArgs(BaseModel):
    project: str = ProjectId
    t: float | int | str = Field(..., description="Timeline time (ms or '0:12.5').")
    width: int = Field(640, ge=64, le=3840)
    show: bool = Field(True, description="Also return the picture itself so it can be looked at (MCP image).")


class SubtitlesArgs(BaseModel):
    project: str = ProjectId
    format: Literal["srt", "vtt", "ass"] = "srt"
    path: str = Field("", max_length=2000, description="Write to this file (in a folder the user named); empty = return the text.")


class ShortArgs(MediaRef):
    start: float | int | str
    end: float | int | str
    name: str = Field("Corto", max_length=120)
    preset: Literal["reels", "shorts", "tiktok", "square", "portrait_4_5"] = "reels"
    captions: bool = True


class StabilizeArgs(BaseModel):
    project: str = ProjectId
    clip: str
    smoothing: int = Field(15, ge=1, le=60)


class FreezeArgs(BaseModel):
    project: str = ProjectId
    clip: str
    at: float | int | str
    length: float | int | str = 2000


class SettingsArgs(BaseModel):
    patch: dict[str, Any] = Field(default_factory=dict, description="Omit to read the settings.")


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    annotations: dict[str, bool]
    run: Callable[[Services, Any], Any]


def _ann(read_only: bool, destructive: bool = False, idempotent: Optional[bool] = None) -> dict[str, bool]:
    return {"readOnlyHint": read_only, "destructiveHint": destructive, "idempotentHint": read_only if idempotent is None else idempotent,
            "openWorldHint": False}


def _t(value: Any) -> Optional[int]:
    if value is None:
        return None
    return parse_time(value) if isinstance(value, str) else int(round(float(value)))


# ---------------- runners

def run_status(svc: Services, a: Empty) -> dict:
    return svc.status()


def run_media_import(svc: Services, a: MediaImportArgs) -> dict:
    if a.folder:
        return media_store.import_folder(svc, a.folder, recursive=a.recursive)
    if not a.path:
        raise LumiereError("Give a path or a folder.")
    m = media_store.import_path(svc, a.path)
    return {k: m[k] for k in ("id", "name", "kind", "duration_ms", "width", "height", "fps", "has_audio", "existing", "path")}


def run_media_list(svc: Services, a: MediaListArgs) -> dict:
    items = media_store.list_media(svc, kind=a.kind, query=a.query, limit=a.limit)
    return {"media": [{"id": m["id"], "name": m["name"], "kind": m["kind"], "duration": ms_to_tc(m["duration_ms"]), "size": f"{m['width']}x{m['height']}",
                       "analysis": m["analysis"], "missing": m["missing"], "proxy": m["proxy"]} for m in items]}


def run_media_get(svc: Services, a: MediaRef) -> dict:
    m = media_store.get(svc, a.media)
    out = {k: v for k, v in m.items() if k != "urls"}
    out["duration"] = ms_to_tc(m["duration_ms"])
    out["analysis_summary"] = {k: analyze.summarize(k, media_store.get_analysis(svc, a.media, k) or {}) for k in m["analysis"] if k in analyze.KINDS}
    lv = media_store.get_analysis(svc, a.media, "levels")
    if lv:
        out["levels"] = lv
    out["jobs"] = [{"id": j["id"], "kind": j["kind"], "state": j["state"], "progress": j["progress"]} for j in svc.jobs.list(state="active", media_id=a.media)]
    return out


def run_media_delete(svc: Services, a: MediaDeleteArgs) -> dict:
    if not a.confirm:
        raise LumiereError("Removing a media needs confirm=true; ask the user first.", code="confirm_required")
    return media_store.delete(svc, a.media, force=a.force)


def run_media_analyze(svc: Services, a: AnalyzeArgs) -> dict:
    return {"media": a.media, "jobs": analyze.schedule(svc, a.media, list(a.kinds), force=a.force, language=a.language, model=a.model)}


def run_media_silences(svc: Services, a: SilencesArgs) -> dict:
    s = analyze.silences_for(svc, a.media, threshold_db=a.threshold_db, min_silence_ms=a.min_silence_ms, margin_ms=a.margin_ms)
    s["ranges"] = [[x, y, f"{ms_to_tc(x)}–{ms_to_tc(y)}"] for x, y in s["ranges"][:400]]
    return s


def run_transcript_get(svc: Services, a: TranscriptArgs) -> dict:
    t = analyze.transcript(svc, a.media)
    if t is None:
        raise LumiereError("No transcript yet: run media_analyze with kinds=['transcript'].", code="no_transcript")
    words = t["words"][a.offset: a.offset + a.limit]
    out: dict[str, Any] = {"media": a.media, "language": t.get("language"), "total_words": len(t["words"]), "offset": a.offset}
    if a.format == "words":
        out["words"] = words
    else:
        lines: list[str] = []
        cur: list[dict[str, Any]] = []
        for w in words:
            cur.append(w)
            if w["text"][-1:] in ".?!" or len(cur) >= 18:
                lines.append(f"[{ms_to_tc(cur[0]['t0'])} {cur[0]['id']}] " + " ".join(x["text"] for x in cur))
                cur = []
        if cur:
            lines.append(f"[{ms_to_tc(cur[0]['t0'])} {cur[0]['id']}] " + " ".join(x["text"] for x in cur))
        out["text"] = "\n".join(lines)
    return out


def run_transcript_fix(svc: Services, a: TranscriptFixArgs) -> dict:
    return analyze.update_words(svc, a.media, a.changes)


def run_highlights(svc: Services, a: HighlightsArgs) -> dict:
    return commands.highlights(svc, a.media, count=a.count, length_ms=int(a.length_s * 1000), mode=a.mode)


def run_media_tag(svc: Services, a: MediaTagArgs) -> dict:
    m = media_store.set_tags(svc, a.media, a.tags)
    return {"media": m["id"], "name": m["name"], "tags": m["tags"]}


def run_project_create(svc: Services, a: ProjectCreateArgs) -> dict:
    if a.template:
        if a.media or a.from_project:
            raise LumiereError("With a template give slots (slot name -> media), not media or from_project.")
        v = project_store.create_from_template(svc, a.name, a.template, a.slots)
        return {**{k: v[k] for k in ("id", "name", "duration", "canvas", "clips", "rev")}, "template": v["template"], "unfilled": v["unfilled"],
                "filled": [{"slot": r["slot"], "media": r["media"], "start": ms_to_tc(r["start"]), "end": ms_to_tc(r["end"]), "rule": r["rule"]}
                           for r in v["filled"]]}
    if a.slots:
        raise LumiereError("slots only go with a template (see template_list).")
    v = project_store.create(svc, a.name, preset=a.preset, media=a.media or None, from_project=a.from_project)
    return {k: v[k] for k in ("id", "name", "duration", "canvas", "clips", "rev")}


def run_template_save(svc: Services, a: TemplateSaveArgs) -> dict:
    return project_store.save_template(svc, a.project, a.name, a.slots)


def run_template_list(svc: Services, a: Empty) -> dict:
    out = []
    for t in project_store.list_templates(svc):
        out.append({"id": t["id"], "name": t["name"], "duration": t["duration"], "canvas": t["canvas"],
                    "slots": [{"slot": s["slot"], "kind": s["track_kind"], "length": ms_to_tc(s["length_ms"]), "sample": s["name"], "rule": s["rule"]}
                              for s in t["slots"]]})
    return {"templates": out}


def run_music_pick(svc: Services, a: MusicPickArgs) -> dict:
    out = music_mod.suggest(svc, a.project, a.folder, recursive=a.recursive, count=a.count)
    if a.add:
        if a.add == "best":
            if not out["tracks"]:
                raise LumiereError("There is no track to add.")
            path = out["tracks"][0]["path"]
        else:
            path = a.add
        out["added"] = commands.run(svc, a.project, "music_add", {"path": path, "volume_db": a.volume_db}, actor="agent")["summary"]
    return out


def run_broll(svc: Services, a: BrollArgs) -> dict:
    try:
        return broll_mod.suggest(svc, a.project, start=_t(a.start), end=_t(a.end), per_sentence=a.per_sentence, use_model=a.use_model, place=a.place)
    except commands.NeedsAnalysis as need:
        return {"done": False, "needs": need.jobs, "message": str(need)}


def run_project_list(svc: Services, a: Empty) -> dict:
    return {"projects": project_store.list_projects(svc)}


def run_project_get(svc: Services, a: ProjectGetArgs) -> dict:
    if a.detail == "full":
        v = project_store.view(svc, a.project)
        return {k: v[k] for k in ("id", "name", "rev", "doc", "media", "issues", "can_undo", "can_redo")}
    out = project_store.outline(svc, a.project)
    out["rev"] = project_store.summary(svc, svc.db.one("SELECT * FROM projects WHERE id = ?", (a.project,)))["rev"]
    p = project_store.doc(svc, a.project)
    styles = {c.id: c.style for t in p.tracks for c in t.clips if c.type == "text" and c.style}
    lo, hi = _t(a.start), _t(a.end)
    tracks = []
    for t in out["tracks"]:
        if a.track and a.track not in (t["id"], t["kind"]):
            continue
        clips = [c for c in t["clips"] if (lo is None or c["end_ms"] > lo) and (hi is None or c["start_ms"] < hi)]
        for c in clips:
            if c["id"] in styles:  # titles: what an assistant needs to restyle them
                st = styles[c["id"]]
                c["style"] = {"position": st.position, "size": st.size, "color": st.color, "animation": st.animation}
        t = dict(t, clip_count=len(clips), clips=clips[: a.max_clips])
        if len(clips) > a.max_clips:
            t["more"] = f"{len(clips) - a.max_clips} more clips until {clips[-1]['end']}: ask with start/end or track"
        tracks.append(t)
    # titles and overlays first: they are few and usually what a request is about
    out["tracks"] = sorted(tracks, key=lambda t: {"text": 0, "audio": 2}.get(t["kind"], 1))
    return out


def run_project_delete(svc: Services, a: ProjectDeleteArgs) -> dict:
    if not a.confirm:
        raise LumiereError("Deleting a project needs confirm=true; ask the user first.", code="confirm_required")
    return project_store.delete(svc, a.project)


def run_edit(svc: Services, a: EditArgs) -> dict:
    return project_store.edit(svc, a.project, a.ops, label=a.label, actor="agent", base_rev=a.base_rev)


def run_history(svc: Services, a: HistoryArgs) -> dict:
    if a.action == "undo":
        return project_store.undo(svc, a.project)
    if a.action == "redo":
        return project_store.redo(svc, a.project)
    if a.action == "restore":
        if a.seq is None:
            raise LumiereError("restore needs seq (from action=list).")
        return project_store.restore(svc, a.project, a.seq)
    return project_store.history(svc, a.project)


def run_command(svc: Services, a: CommandArgs) -> dict:
    try:
        return commands.run(svc, a.project, a.command, a.args, actor="agent", preview=a.preview)
    except commands.NeedsAnalysis as need:
        return {"done": False, "needs": need.jobs, "message": str(need)}


def run_timeline_transcript(svc: Services, a: TimelineTranscriptArgs) -> dict:
    p = project_store.doc(svc, a.project)
    out = commands.timeline_transcript(svc, p, track=a.track)
    words = out["words"]
    out["total_words"] = len(words)
    out["words"] = [{"id": w["id"], "media": w["media"], "text": w["text"], "t": ms_to_tc(w["t"])} for w in words[a.offset: a.offset + a.limit]]
    return out


def run_text_cut(svc: Services, a: TextCutArgs) -> dict:
    try:
        return commands.run(svc, a.project, "cut_words", {"media": a.media, "word_ids": a.word_ids or None, "text": a.phrase or None, "keep": a.keep},
                            actor="agent")
    except commands.NeedsAnalysis as need:
        return {"done": False, "needs": need.jobs, "message": str(need)}


def run_plan_create(svc: Services, a: PlanCreateArgs) -> dict:
    return plan_mod.create(svc, a.project, a.instruction, use_model=a.use_model)


def run_plan_apply(svc: Services, a: PlanApplyArgs) -> dict:
    if a.steps is not None:
        plan_mod.update(svc, a.plan, a.steps)
    plan = plan_mod.get(svc, a.plan)
    if plan["state"] != "draft":
        raise LumiereError(f"The plan is {plan['state']}.")
    job = svc.jobs.submit("plan_apply", {"plan": a.plan, "wait_s": a.wait_s}, label=f"Plan: {plan['instruction'][:60]}", project_id=plan["project"])
    return {"job": job["id"], "state": job["state"], "hint": "Follow it with job_status; the result lists the steps done and any renders queued."}


def run_render(svc: Services, a: RenderArgs) -> dict:
    lufs: Any = "default" if a.lufs == -999 else a.lufs
    job = svc.start_render(a.project, preset=a.preset, start=_t(a.start), end=_t(a.end), filename=a.filename, folder=a.folder, lufs=lufs,
                           subtitles=a.subtitles, mode=a.mode)
    return {"job": job["id"], "state": job["state"], "label": job["label"]}


def run_job_status(svc: Services, a: JobArgs) -> dict:
    if a.job:
        return svc.jobs.get(a.job)
    return {"active": svc.jobs.list(state="active"), "recent": svc.jobs.list(limit=10)}


def run_job_cancel(svc: Services, a: JobCancelArgs) -> dict:
    return svc.jobs.cancel(a.job)


def run_renders(svc: Services, a: RendersArgs) -> dict:
    return {"renders": runner.renders_list(svc, a.project)}


def run_frame(svc: Services, a: FrameArgs) -> dict:
    t = _t(a.t) or 0
    path = runner.render_frame(svc, a.project, t, width=a.width)
    out: dict = {"path": str(path), "t": ms_to_tc(t), "url": f"/api/frames/{path.name}", "shows": _frame_layers(svc, a.project, t)}
    if a.show:
        data = path.read_bytes()
        if a.width > 960:  # keep the picture light; the file on disk has the full size
            data = runner.render_frame(svc, a.project, t, width=960).read_bytes()
        out["_image"] = {"mime": "image/jpeg", "data": base64.b64encode(data).decode("ascii")}
    return out


def _frame_layers(svc: Services, project: str, t: int) -> list[dict]:
    """What the project draws at t, top layer first, so an assistant looking at the frame knows which text comes from the
    edit (titles, burned-in captions) and which was already in the footage."""
    p = project_store.doc(svc, project)
    layers: list[dict] = []
    if p.captions.enabled:
        try:
            words = commands.timeline_transcript(svc, p)["words"]
        except Exception:  # noqa: BLE001 - no transcript yet: captions draw nothing
            words = []
        near = [w["text"] for w in words if abs(w["t"] - t) <= 1500]
        layers.append({"layer": "captions", "style": p.captions.style, "position": p.captions.position,
                       "text_near": " ".join(near)[:200], "note": "burned in by this project from the transcript"})
    for track in reversed(p.tracks):
        if track.hidden or track.kind == "audio":
            continue
        for c in track.clips:
            if c.start <= t < c.end:
                item: dict = {"layer": "text" if c.type == "text" else track.role, "track": track.id, "clip": c.id}
                if c.type == "text":
                    item.update(text=(c.text or "")[:200], position=c.style.position if c.style else None)
                else:
                    info = svc.db.one("SELECT name FROM media WHERE id = ?", (c.media,))
                    item["media"] = info["name"] if info else c.media
                layers.append(item)
    return layers


def run_subtitles(svc: Services, a: SubtitlesArgs) -> dict:
    text, _ = runner.subtitles_export(svc, a.project, a.format)
    if a.path:
        dest = Path(a.path).expanduser()
        media_store._check_root(svc, dest.parent)
        if not dest.parent.is_dir():
            raise LumiereError(f"The folder {dest.parent} does not exist.")
        dest.write_text(text, encoding="utf-8")
        return {"path": str(dest), "bytes": len(text.encode())}
    return {"format": a.format, "text": text}


def run_short(svc: Services, a: ShortArgs) -> dict:
    return commands.short_from_range(svc, a.media, _t(a.start) or 0, _t(a.end) or 0, name=a.name, preset=a.preset, with_captions=a.captions)


def run_stabilize(svc: Services, a: StabilizeArgs) -> dict:
    project_store.doc(svc, a.project).find(a.clip)
    job = svc.jobs.submit("stabilize", {"project": a.project, "clip": a.clip, "smoothing": a.smoothing}, label="Estabilizar clip", project_id=a.project)
    return {"job": job["id"], "state": job["state"]}


def run_freeze(svc: Services, a: FreezeArgs) -> dict:
    return derive.freeze_frame(svc, a.project, a.clip, _t(a.at) or 0, _t(a.length) or 2000)


def run_presets(svc: Services, a: Empty) -> dict:
    return {"canvas_presets": PRESETS, "export_presets": runner.export_presets(), "transitions": list(TRANSITIONS),
            "effects": {k: {p: v[0] for p, v in spec.items()} for k, spec in fx.SPECS.items()},
            "caption_styles": ["clean", "bold", "karaoke", "pop", "boxed", "minimal"], "operations": OP_NAMES, "operation_fields": op_reference().split("\n"), "commands": plan_mod.COMMAND_DOCS}


def run_settings(svc: Services, a: SettingsArgs) -> dict:
    return svc.update_settings(a.patch) if a.patch else svc.get_settings()


TOOLS: list[Tool] = [
    Tool("lumiere_status", "Video editor status: ffmpeg, GPU encoder, speech model, jobs. Estado del editor de vídeo.\n"
         "Sinónimos: estado, capacidades, qué puede hacer.\nKeywords: status, video editor, editor de vídeo.", Empty, _ann(True), run_status),
    Tool("media_import", "Import a video, audio or image file (or a folder) by path; nothing is copied. Importar vídeo.\n"
         "Makes a proxy, filmstrip and waveform in the background. Sinónimos: añadir vídeo, cargar, abrir archivo.\nKeywords: import, add media, video file.",
         MediaImportArgs, _ann(False, False, True), run_media_import),
    Tool("media_list", "List the media library (videos, audios, images) with analyses done. Biblioteca de medios.\n"
         "Sinónimos: mis vídeos, archivos importados.\nKeywords: media, library, list.", MediaListArgs, _ann(True), run_media_list),
    Tool("media_get", "One media in detail: size, length, streams, levels, analyses and running jobs. Ver medio.\n"
         "Keywords: media info, probe.", MediaRef, _ann(True), run_media_get),
    Tool("media_delete", "Remove a media from the library (needs confirm=true). Quitar de la biblioteca.\n"
         "The original file stays. Keywords: delete media.", MediaDeleteArgs, _ann(False, True, True), run_media_delete),
    Tool("media_analyze", "Run analyses on a media: transcript, scenes, beats, loudness, motion, focus. Analizar vídeo.\n"
         "Background jobs; results are cached. Sinónimos: transcribir, detectar escenas, ritmo.\nKeywords: analyze, transcribe, whisper, scenes, beats.",
         AnalyzeArgs, _ann(False, False, True), run_media_analyze),
    Tool("media_silences", "Silent ranges of a media (automatic threshold from the noise floor). Silencios.\n"
         "Preview before remove_silences. Keywords: silence, pauses, dead air.", SilencesArgs, _ann(True), run_media_silences),
    Tool("transcript_get", "Read a media's transcript (text with times and word ids, or words). Transcripción.\n"
         "Sinónimos: qué dice, texto del vídeo.\nKeywords: transcript, words, speech.", TranscriptArgs, _ann(True), run_transcript_get),
    Tool("transcript_fix", "Correct transcript words (captions use the corrected text). Corregir transcripción.\n"
         "Keywords: fix transcript, typo, captions text.", TranscriptFixArgs, _ann(False, False, True), run_transcript_fix),
    Tool("highlights_find", "Find the best moments of a long video (sound, motion, speech; mode=model reads it). Mejores momentos.\n"
         "mode=model asks the local model for hooks, punchlines and complete thoughts and merges them with the signals, with reasons.\n"
         "Sinónimos: highlights, clips virales, momentos clave, gameplay.\nKeywords: highlights, best moments, clips, hook, punchline.", HighlightsArgs, _ann(True), run_highlights),
    Tool("media_tag", "Label a media with keywords (replaces its tags); b-roll suggestions match them. Etiquetar medio.\n"
         "Sinónimos: etiquetas, palabras clave, describir clip.\nKeywords: tags, labels, keywords, b-roll library.", MediaTagArgs, _ann(False, False, True), run_media_tag),
    Tool("short_from_range", "Make a vertical short (reframed, captions) from one range of a media. Crear corto vertical.\n"
         "Sinónimos: reel, tiktok, short desde un momento.\nKeywords: short, reel, vertical clip.", ShortArgs, _ann(False), run_short),
    Tool("project_create", "Create an editing project (canvas preset and media, or a template with slots). Nuevo proyecto de vídeo.\n"
         "Presets: reels, youtube, square... With template + slots {name: media} it fills a saved template (template_list).\n"
         "Keywords: new project, timeline, from template, slots.", ProjectCreateArgs, _ann(False), run_project_create),
    Tool("template_save", "Save a project as a template with replaceable slots (intro, main, outro...). Guardar plantilla.\n"
         "Titles, captions, music and effects stay; slot clips are replaced later with project_create template+slots.\n"
         "Sinónimos: plantilla, formato reutilizable, intro y outro fijos.\nKeywords: template, slots, reusable edit.", TemplateSaveArgs, _ann(False), run_template_save),
    Tool("template_list", "List the project templates with their slots. Plantillas de vídeo.\n"
         "Keywords: templates, slots, reusable.", Empty, _ann(True), run_template_list),
    Tool("project_list", "List the editing projects. Proyectos de vídeo.\nKeywords: projects, list.", Empty, _ann(True), run_project_list),
    Tool("project_get", "Read a project's timeline: tracks, clips with ids and times, captions, issues. Ver timeline.\n"
         "Titles first; filter by track or time on long timelines. Keywords: timeline, outline, clips, tracks, titles.", ProjectGetArgs, _ann(True), run_project_get),
    Tool("project_delete", "Delete a project and its history (needs confirm=true). Borrar proyecto.\nKeywords: delete project.",
         ProjectDeleteArgs, _ann(False, True, True), run_project_delete),
    Tool("timeline_edit", "Edit the timeline with operations (split, trim, move, delete, titles, speed...). Editar timeline.\n"
         "All or nothing, one undo step. Sinónimos: cortar, recortar, mover, añadir texto, título, rótulo.\n"
         "Keywords: edit, cut, trim, split, title, text overlay, ops.",
         EditArgs, _ann(False, True, False), run_edit),
    Tool("timeline_history", "Undo, redo, list or restore history steps of a project. Deshacer.\n"
         "Sinónimos: deshacer, rehacer, historial, volver atrás.\nKeywords: undo, redo, history.", HistoryArgs, _ann(False, False, False), run_history),
    Tool("edit_command", "Smart edits: remove_silences, remove_fillers, reframe, captions, beat_sync... Edición inteligente.\n"
         "Sinónimos: quitar silencios, muletillas, vertical, subtítulos, al ritmo.\nKeywords: jump cut, captions, reframe, beat sync.",
         CommandArgs, _ann(False, True, False), run_command),
    Tool("timeline_transcript", "Words heard on the timeline, in order, with ids: the text editor view. Texto del montaje.\n"
         "Keywords: transcript, text-based editing.", TimelineTranscriptArgs, _ann(True), run_timeline_transcript),
    Tool("text_cut", "Text-based editing: cut words or a phrase (or keep only them) from the video. Editar por texto.\n"
         "Sinónimos: borrar frase, quitar lo que dice, quedarse con.\nKeywords: text edit, cut words, transcript edit.",
         TextCutArgs, _ann(False, True, False), run_text_cut),
    Tool("plan_create", "Turn the user's words into an editable edit plan (nothing changes yet). Plan de edición.\n"
         "Sinónimos: edítalo así, haz que, instrucciones.\nKeywords: plan, natural language edit, instructions.", PlanCreateArgs, _ann(False), run_plan_create),
    Tool("plan_apply", "Apply a plan (optionally edited) as one undo step; exports in it are queued. Aplicar plan.\n"
         "Runs in the background. Keywords: apply plan, run.", PlanApplyArgs, _ann(False, True, False), run_plan_apply),
    Tool("music_pick", "Rank the audio files of a folder as background music for an edit (tempo, length, energy). Elegir música.\n"
         "Fits the edit's length and cuts per minute, with reasons; add='best' puts it under the edit, trimmed, faded, ducking.\n"
         "Sinónimos: música de fondo, banda sonora, canción para el vídeo.\nKeywords: background music, bpm, tempo, soundtrack, ducking.",
         MusicPickArgs, _ann(False), run_music_pick),
    Tool("broll_suggest", "Suggest library clips as b-roll for each sentence (or a range) of the edit. Sugerir b-roll.\n"
         "Matches what clips say, their names and tags; place='best' puts them as muted overlays; add_overlay op places one.\n"
         "Sinónimos: planos de recurso, imágenes de apoyo, cubrir con vídeo.\nKeywords: b-roll, cutaway, overlay, stock footage, keywords.",
         BrollArgs, _ann(False), run_broll),
    Tool("render_start", "Export the project to a video file (MP4, HEVC, ProRes, GIF, MP3...). Exportar vídeo.\n"
         "GPU encoder when available. Sinónimos: renderizar, sacar el vídeo, descargar.\nKeywords: render, export, mp4.", RenderArgs, _ann(False), run_render),
    Tool("job_status", "State and progress of a background job (or the active ones). Estado de tareas.\n"
         "Keywords: job, progress, render status.", JobArgs, _ann(True), run_job_status),
    Tool("job_cancel", "Cancel a background job (render, transcription, analysis). Cancelar tarea.\nKeywords: cancel, stop.",
         JobCancelArgs, _ann(False, False, True), run_job_cancel),
    Tool("renders_list", "Exported files with their quality check (duration, size, loudness). Exportaciones.\n"
         "Keywords: renders, exports, output files.", RendersArgs, _ann(True), run_renders),
    Tool("frame_snapshot", "Save the frame the timeline shows at a time as an image (exactly as rendered). Fotograma.\n"
         "Use it to look at the edit. Keywords: frame, snapshot, preview image.", FrameArgs, _ann(False, False, True), run_frame),
    Tool("subtitles_export", "Export the captions as SRT, VTT or ASS (to a file or as text). Exportar subtítulos.\n"
         "Keywords: srt, vtt, subtitles file.", SubtitlesArgs, _ann(False, False, True), run_subtitles),
    Tool("clip_stabilize", "Stabilize a shaky clip (background job; the clip is pointed at the stable copy). Estabilizar.\n"
         "Keywords: stabilize, shaky, gimbal.", StabilizeArgs, _ann(False), run_stabilize),
    Tool("clip_freeze", "Insert a freeze frame of a clip at a time. Congelar imagen.\nKeywords: freeze frame, still.", FreezeArgs, _ann(False), run_freeze),
    Tool("presets_list", "Canvas and export presets, transitions, effects, caption styles, operations. Opciones.\n"
         "Keywords: presets, effects, transitions, vocabulary.", Empty, _ann(True), run_presets),
    Tool("settings", "Read or change settings (speech model, language, GPU decoding, export folder). Ajustes.\n"
         "Keywords: settings, whisper model, config.", SettingsArgs, _ann(False, False, True), run_settings),
]

TOOLS_BY_NAME = {t.name: t for t in TOOLS}
RESULT_CAP = 24_000


def tool_catalog() -> list[dict]:
    return [{"name": t.name, "description": t.description, "annotations": t.annotations, "inputSchema": t.input_model.model_json_schema(by_alias=True)}
            for t in TOOLS]


def cap_result(result: Any, limit: int = RESULT_CAP) -> Any:
    if not isinstance(result, dict) or len(json.dumps(result, ensure_ascii=False, default=str)) <= limit:
        return result
    cut: list[str] = []
    for _ in range(40):
        if len(json.dumps(result, ensure_ascii=False, default=str)) <= limit:
            break
        best: Optional[tuple[int, str]] = None
        for key, value in result.items():
            if isinstance(value, list) and len(value) > 1:
                n = len(json.dumps(value, ensure_ascii=False, default=str))
                if best is None or n > best[0]:
                    best = (n, key)
        if best is None:
            text_key = max((k for k, v in result.items() if isinstance(v, str)), key=lambda k: len(result[k]), default=None)
            if text_key and len(result[text_key]) > 1000:
                result[text_key] = result[text_key][: len(result[text_key]) // 2] + "…"
                cut.append(text_key)
                continue
            break
        result[best[1]] = result[best[1]][: max(1, len(result[best[1]]) // 2)]
        cut.append(best[1])
    if cut:
        result["truncated"] = True
        result["truncated_fields"] = sorted(set(cut))
        result["hint"] = "Trimmed to fit: page with offset/limit or ask for less detail."
    return result


def call_tool(svc: Services, name: str, arguments: dict | None, *, caller: Optional[str] = None, cap: bool = False) -> Any:
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        raise KeyError(f"Unknown tool: {name}")
    args = tool.input_model.model_validate(arguments or {})
    result = tool.run(svc, args)
    image = result.pop("_image", None) if isinstance(result, dict) else None
    if cap:
        result = cap_result(result)
    if image:
        result["_image"] = image  # a picture is never trimmed; the MCP bridge turns it into an image block
    return result
