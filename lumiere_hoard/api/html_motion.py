"""The HTML motion workshop, sharing the service used by assistant tools."""
from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from .. import family_events, projects
from ..errors import NotFound
from ..html_motion import HtmlMotion
from ..html_motion_args import HtmlMotionSaveArgs, HtmlMotionRestoreArgs
from .deps import services

router = APIRouter(prefix="/api/html-motion", tags=["HTML motion"])


def _store(request: Request) -> HtmlMotion:
    return HtmlMotion(services(request).config.data_dir)


@router.get("")
def list_compositions(request: Request):
    return _store(request).list()


@router.post("")
def save(request: Request, body: HtmlMotionSaveArgs):
    if body.project_id:
        projects.doc(services(request), body.project_id)
    return _store(request).save(**body.model_dump())


@router.get("/{composition}")
def get(request: Request, composition: str, revision: int | None = Query(None, ge=1)):
    store = _store(request)
    manifest = store.get(composition, revision)
    revisions = sorted(int(p.name) for p in store.folder(composition).iterdir() if p.is_dir() and p.name.isdigit())
    return {**manifest, "html": store.source(manifest), "revisions": revisions}


@router.post("/restore")
def restore(request: Request, body: HtmlMotionRestoreArgs):
    return _store(request).restore(**body.model_dump())


@router.get("/{composition}/revisions/{revision}/source")
def source(request: Request, composition: str, revision: int):
    store = _store(request)
    manifest = store.get(composition, revision)
    return FileResponse(manifest["source_path"], media_type="text/html", filename="composition.html", headers={"Cache-Control": "no-store"})


@router.get("/{composition}/revisions/{revision}/frame")
def frame(request: Request, composition: str, revision: int, at: float = Query(0, ge=0)):
    data, info = _store(request).frame(composition, at, revision)
    return Response(data, media_type="image/png", headers={"Cache-Control": "no-store", "X-Frame-Sha256": info["frame_sha256"]})


@router.post("/{composition}/render")
def render(request: Request, composition: str, revision: int | None = Query(None, ge=1)):
    return _store(request).queue_render(services(request), composition, revision)


@router.get("/{composition}/revisions/{revision}/render/{job}")
def video(request: Request, composition: str, revision: int, job: str):
    store = _store(request)
    store.get(composition, revision)
    result = services(request).jobs.get(job)
    if result["state"] != "done" or result["kind"] != "html_motion" or result["params"] != {"composition": composition, "revision": revision}:
        raise NotFound("This HTML video export is not ready.")
    path = store.folder(composition) / str(revision) / f"render-{job}.mp4"
    if not path.is_file():
        raise NotFound("HTML video export is missing.")
    return FileResponse(path, media_type="video/mp4", headers={"Cache-Control": "no-store"})


class ReceiveBody(BaseModel):
    project: str = ""


@router.post("/{composition}/receive")
def receive(request: Request, composition: str, body: ReceiveBody):
    manifest = _store(request).get(composition)
    if not manifest.get("render_path"):
        raise NotFound("Render the current HTML revision before adding it to the library.")
    return family_events.receive_media(services(request), path=manifest["render_path"], name=manifest["name"],
                                       project=body.project, source="lumiere")
