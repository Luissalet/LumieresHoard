"""Projects: the timeline document, its revision counter and the undo / redo history."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any, Optional

from . import media as media_store
from .errors import Conflict, LumiereError, NotFound
from .ops import PRESETS, apply_ops
from .timeline import Project, load, new_project, validate
from .util import clip, dumps, ms_to_tc, new_id

if TYPE_CHECKING:
    from .services import Services

HISTORY_LIMIT = 300


def _row(svc: "Services", project_id: str):
    row = svc.db.one("SELECT * FROM projects WHERE id = ?", (project_id,))
    if row is None:
        raise NotFound(f"No project {project_id}.")
    return row


def doc(svc: "Services", project_id: str) -> Project:
    return load(json.loads(_row(svc, project_id)["doc"]))


def media_lookup(svc: "Services"):
    cache: dict[str, Optional[dict]] = {}

    def look(mid: str) -> Optional[dict[str, Any]]:
        if mid not in cache:
            cache[mid] = media_store.lookup(svc, mid)
        return cache[mid]

    return look


def summary(svc: "Services", row) -> dict[str, Any]:
    p = load(json.loads(row["doc"]))
    clips = sum(len(t.clips) for t in p.tracks)
    return {"id": row["id"], "name": row["name"], "rev": row["rev"], "duration_ms": p.duration, "duration": ms_to_tc(p.duration),
            "canvas": f"{p.canvas.width}x{p.canvas.height}@{p.canvas.fps:g}", "clips": clips, "tracks": len(p.tracks),
            "is_template": bool(row["is_template"]), "updated_ts": row["updated_ts"], "created_ts": row["created_ts"],
            "thumb": _thumb(svc, p)}


def _thumb(svc: "Services", p: Project) -> Optional[str]:
    main = p.main_track()
    for c in (main.clips if main else []):
        if c.media:
            return f"/api/media/{c.media}/poster"
    return None


def list_projects(svc: "Services", templates: Optional[bool] = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM projects"
    args: tuple = ()
    if templates is not None:
        sql += " WHERE is_template = ?"
        args = (int(templates),)
    return [summary(svc, r) for r in svc.db.query(sql + " ORDER BY updated_ts DESC", args)]


def view(svc: "Services", project_id: str) -> dict[str, Any]:
    row = _row(svc, project_id)
    p = load(json.loads(row["doc"]))
    look = media_lookup(svc)
    used = {}
    for mid in sorted(p.media_ids()):
        media_store.ensure_color_space(svc, mid)
        info = look(mid)
        if info:
            used[mid] = {k: info[k] for k in ("id", "name", "kind", "duration_ms", "width", "height", "fps", "has_audio", "has_video", "missing", "proxy", "urls", "color_space")}
    can_undo = row["head"] > 1
    can_redo = svc.db.one("SELECT 1 FROM history WHERE project_id = ? AND seq > ?", (project_id, row["head"])) is not None
    return {**summary(svc, row), "doc": p.dump(), "media": used, "issues": validate(p, look), "can_undo": can_undo, "can_redo": can_redo,
            "undo_label": _label(svc, project_id, row["head"]) if can_undo else None,
            "redo_label": _label(svc, project_id, row["head"] + 1) if can_redo else None}


def _label(svc: "Services", project_id: str, seq: int) -> Optional[str]:
    row = svc.db.one("SELECT label FROM history WHERE project_id = ? AND seq = ?", (project_id, seq))
    return row["label"] if row else None


def create(svc: "Services", name: str, *, preset: Optional[str] = None, width: Optional[int] = None, height: Optional[int] = None,
           fps: Optional[float] = None, media: Optional[list[str]] = None, template: bool = False, from_project: Optional[str] = None) -> dict[str, Any]:
    if from_project:
        p = doc(svc, from_project)
    else:
        spec = PRESETS.get(preset or "youtube")
        if preset and spec is None:
            raise LumiereError(f"Unknown preset {preset!r}. Known: {', '.join(PRESETS)}.")
        p = new_project(width or spec["width"], height or spec["height"], fps or spec["fps"])
    pid = new_id("prj")
    now = time.time()
    with svc.db.transaction() as conn:
        conn.execute("INSERT INTO projects(id, name, doc, rev, head, is_template, created_ts, updated_ts) VALUES (?, ?, ?, 1, 1, ?, ?, ?)",
                     (pid, clip(name or "Proyecto", 120), dumps(p.dump()), int(template), now, now))
        conn.execute("INSERT INTO history(project_id, seq, label, actor, doc, ts) VALUES (?, 1, ?, 'ui', ?, ?)", (pid, "Crear", dumps(p.dump()), now))
    if media:
        edit(svc, pid, [{"op": "add_media", "media": m} for m in media], label="Añadir medios")
    svc.emit("lumiere.project.created", {"id": pid, "name": clip(name, 80)})
    return view(svc, pid)


def rename(svc: "Services", project_id: str, name: str) -> dict[str, Any]:
    _row(svc, project_id)
    svc.db.execute("UPDATE projects SET name = ?, updated_ts = ? WHERE id = ?", (clip(name, 120), time.time(), project_id))
    return summary(svc, _row(svc, project_id))


def set_template(svc: "Services", project_id: str, value: bool) -> dict[str, Any]:
    _row(svc, project_id)
    svc.db.execute("UPDATE projects SET is_template = ? WHERE id = ?", (int(value), project_id))
    return summary(svc, _row(svc, project_id))


def delete(svc: "Services", project_id: str) -> dict[str, Any]:
    row = _row(svc, project_id)
    svc.db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    return {"deleted": project_id, "name": row["name"]}


def save(svc: "Services", project_id: str, p: Project, label: str, actor: str = "ui", base_rev: Optional[int] = None) -> int:
    """Store a new version: drops any redo branch, appends to the history, bumps the revision."""
    now = time.time()
    with svc.db.transaction() as conn:
        row = conn.execute("SELECT rev, head FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise NotFound(f"No project {project_id}.")
        if base_rev is not None and base_rev != row["rev"]:
            raise Conflict(f"The project changed (revision {row['rev']}, you sent {base_rev}). Read it again and repeat the edit.")
        head = row["head"] + 1
        conn.execute("DELETE FROM history WHERE project_id = ? AND seq >= ?", (project_id, head))
        conn.execute("INSERT INTO history(project_id, seq, label, actor, doc, ts) VALUES (?, ?, ?, ?, ?, ?)",
                     (project_id, head, clip(label, 200), actor, dumps(p.dump()), now))
        conn.execute("DELETE FROM history WHERE project_id = ? AND seq <= ?", (project_id, head - HISTORY_LIMIT))
        conn.execute("UPDATE projects SET doc = ?, rev = rev + 1, head = ?, updated_ts = ? WHERE id = ?", (dumps(p.dump()), head, now, project_id))
        return row["rev"] + 1


def edit(svc: "Services", project_id: str, ops: list[dict[str, Any]], *, label: str = "", actor: str = "ui",
         base_rev: Optional[int] = None) -> dict[str, Any]:
    if not ops:
        raise LumiereError("No operations.")
    current = doc(svc, project_id)
    look = media_lookup(svc)
    new, results = apply_ops(current, ops, look)
    rev = save(svc, project_id, new, label or describe(ops), actor, base_rev)
    issues = validate(new, look)
    return {"project": project_id, "rev": rev, "results": results, "duration_ms": new.duration, "duration": ms_to_tc(new.duration),
            "issues": issues}


def describe(ops: list[dict[str, Any]]) -> str:
    names = {"add_media": "Añadir clip", "add_text": "Añadir texto", "split": "Dividir", "trim": "Recortar", "move": "Mover", "delete": "Borrar",
             "delete_range": "Borrar tramo", "cut_source": "Cortar", "keep_source": "Quedarse con tramos", "set": "Cambiar clip",
             "speed": "Velocidad", "transition": "Transición", "filter_add": "Efecto", "filter_remove": "Quitar efecto", "track_add": "Nueva pista",
             "track_set": "Pista", "track_delete": "Borrar pista", "canvas": "Formato", "marker_add": "Marcador", "marker_delete": "Quitar marcadores",
             "captions": "Subtítulos", "duplicate": "Duplicar", "detach_audio": "Separar audio", "close_gaps": "Cerrar huecos",
             "replace_media": "Sustituir medio", "sequence": "Secuencia", "keyframes": "Animación", "slip": "Deslizar contenido", "roll": "Mover corte",
             "insert_clips": "Pegar", "notes": "Notas"}
    first = names.get(str(ops[0].get("op")), str(ops[0].get("op")))
    return first if len(ops) == 1 else f"{first} (+{len(ops) - 1})"


def undo(svc: "Services", project_id: str) -> dict[str, Any]:
    return _move(svc, project_id, -1)


def redo(svc: "Services", project_id: str) -> dict[str, Any]:
    return _move(svc, project_id, +1)


def _move(svc: "Services", project_id: str, step: int) -> dict[str, Any]:
    with svc.db.transaction() as conn:
        row = conn.execute("SELECT head FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise NotFound(f"No project {project_id}.")
        target = row["head"] + step
        h = conn.execute("SELECT doc, label FROM history WHERE project_id = ? AND seq = ?", (project_id, target)).fetchone()
        if h is None or target < 1:
            raise LumiereError("Nothing to redo." if step > 0 else "Nothing to undo.", code="no_history")
        conn.execute("UPDATE projects SET doc = ?, head = ?, rev = rev + 1, updated_ts = ? WHERE id = ?", (h["doc"], target, time.time(), project_id))
        label = h["label"] if step > 0 else _label(svc, project_id, row["head"])
    return {"project": project_id, "undone" if step < 0 else "redone": label, **{k: v for k, v in view(svc, project_id).items() if k in ("rev", "duration_ms", "can_undo", "can_redo", "undo_label", "redo_label")}}


def history(svc: "Services", project_id: str, limit: int = 60) -> dict[str, Any]:
    row = _row(svc, project_id)
    items = [{"seq": r["seq"], "label": r["label"], "actor": r["actor"], "ts": r["ts"], "current": r["seq"] == row["head"]}
             for r in svc.db.query("SELECT seq, label, actor, ts FROM history WHERE project_id = ? ORDER BY seq DESC LIMIT ?", (project_id, limit))]
    return {"project": project_id, "head": row["head"], "items": items}


def restore(svc: "Services", project_id: str, seq: int) -> dict[str, Any]:
    """Go back to any point in the history as a new step (nothing is lost)."""
    h = svc.db.one("SELECT doc, label FROM history WHERE project_id = ? AND seq = ?", (project_id, seq))
    if h is None:
        raise NotFound(f"No history step {seq}.")
    p = load(json.loads(h["doc"]))
    rev = save(svc, project_id, p, f"Volver a «{h['label']}»")
    return {"project": project_id, "rev": rev}


def outline(svc: "Services", project_id: str) -> dict[str, Any]:
    """A compact text-like description of the timeline for an assistant: tracks, clips with times and sources."""
    p = doc(svc, project_id)
    look = media_lookup(svc)
    tracks = []
    for t in p.tracks:
        clips = []
        for c in t.clips:
            item: dict[str, Any] = {"id": c.id, "start": ms_to_tc(c.start), "end": ms_to_tc(c.end), "start_ms": c.start, "end_ms": c.end}
            if c.type == "text":
                item["text"] = clip(c.text, 80)
            else:
                info = look(c.media) or {}
                item.update({"media": c.media, "name": clip(info.get("name", ""), 40), "src": f"{ms_to_tc(c.src_in)}–{ms_to_tc(c.src_out)}"})
                if c.speed != 1:
                    item["speed"] = c.speed
                if c.mute:
                    item["mute"] = True
                if c.transform.fit != "contain" or c.transform.scale != 1:
                    item["fit"] = c.transform.fit
                if c.reframe:
                    item["reframed"] = True
            if c.filters:
                item["effects"] = [f.type for f in c.filters]
            if c.transition_in:
                item["transition"] = f"{c.transition_in.type} {c.transition_in.dur}ms"
            clips.append(item)
        tracks.append({"id": t.id, "kind": t.kind, "role": t.role, "name": t.name, "muted": t.muted, "hidden": t.hidden, "locked": t.locked,
                       "clips": clips})
    return {"project": project_id, "canvas": p.canvas.model_dump(), "duration": ms_to_tc(p.duration), "duration_ms": p.duration,
            "length_mode": p.length_mode, "tracks": tracks, "markers": [m.model_dump() for m in p.markers[:200]],
            "captions": p.captions.model_dump(), "issues": validate(p, look)}
