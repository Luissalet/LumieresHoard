"""Wiring: database, ffmpeg tools, background jobs, Hoard Link (the local model), the family bus and settings.
Every provider is injectable so the app runs offline in tests."""

from __future__ import annotations

import dataclasses
import logging
import secrets
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Optional

from . import APP_ID, SERVICE, __version__
from . import analyze, derive
from . import speakers as speakers_mod
from . import ffmpeg as ff
from . import media as media_store
from . import plan as plan_mod
from .analysis import faces
from .config import Config
from .db import Database
from .errors import LumiereError
from .hoard_link import family
from .hoard_link.config import LinkConfig
from .jobs import JobQueue
from .render import runner, sequences
from .util import clip

log = logging.getLogger("lumiere")

SETTINGS = {
    "model": "",                 # preferred LLM for plans (empty = Hoard Link decides)
    "whisper_model": "",         # empty = large-v3-turbo on GPU, small on CPU
    "whisper_device": "auto",    # auto | cuda | cpu
    "transcript_language": "",   # empty = detect
    "hwdec": "auto",             # auto | on | off: GPU decoding of sources while rendering
    "default_export": "final",
    "export_folder": "",         # empty = data/renders
    "auto_transcribe": "off",    # on: transcribe every imported media with speech
    "face_detector": "auto",     # auto | yunet | haar | saliency: who finds the subject when reframing
}


def write_token(config: Config) -> str:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    try:
        existing = config.token_path.read_text(encoding="utf-8").strip()
    except OSError:
        existing = ""
    if len(existing) >= 32:
        return existing
    token = secrets.token_hex(32)
    config.token_path.write_text(token, encoding="utf-8")
    try:
        config.token_path.chmod(0o600)
    except OSError:
        pass
    return token


class Services:
    def __init__(self, config: Config, *, link: Any = None, emit_fn: Optional[Callable[[str, dict], None]] = None, tools: Optional[ff.Tools] = None,
                 inline_jobs: bool = False):
        self.config = config
        self.started_at = time.time()
        config.data_dir.mkdir(parents=True, exist_ok=True)
        for d in (config.cache_dir, config.renders_dir, config.work_dir, config.uploads_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.token = write_token(config)
        try:
            config.url_path.write_text(f"http://127.0.0.1:{config.port}", encoding="utf-8")
        except OSError:
            pass
        self.db = Database(config.db_path)
        self._tools = tools
        self._injected_link = link
        self._link: Any = None
        self.link_sync: Any = link if link is not None else self._build_link()
        self._emit = emit_fn
        from .analysis import speech

        self.transcriber: Callable[..., dict[str, Any]] = speech.transcribe  # tests replace it
        self.model_fetch: Callable[[str, Path], None] = faces.download  # downloads small model files; tests replace it
        self.jobs = JobQueue(self.db, config.workers, on_done=self._job_done, run_inline=inline_jobs)
        self.jobs.register("prepare", lambda ctx: media_store.prepare_job(self, ctx))
        self.jobs.register("analyze", lambda ctx: analyze.analyze_job(self, ctx))
        self.jobs.register("transcribe", lambda ctx: analyze.transcribe_job(self, ctx))
        self.jobs.register("diarize", lambda ctx: speakers_mod.diarize_job(self, ctx))
        self.jobs.register("render", lambda ctx: runner.render_job(self, ctx))
        self.jobs.register("copy_cut", lambda ctx: runner.copy_cut_job(self, ctx))
        self.jobs.register("stabilize", lambda ctx: derive.stabilize_job(self, ctx))
        self.jobs.register("plan_apply", lambda ctx: plan_mod.apply_job(self, ctx))
        self.jobs.register("sequence", lambda ctx: sequences.prepare_job(self, ctx))

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        shutil.rmtree(self.config.work_dir, ignore_errors=True)
        self.config.work_dir.mkdir(parents=True, exist_ok=True)
        self.jobs.start()

    def stop(self) -> None:
        self.jobs.stop()
        if self._link is not None:
            try:
                self.link_sync.close()
            except Exception:  # noqa: BLE001
                pass
        self.db.close()

    def _build_link(self) -> Any:
        from .hoard_link.link import Link

        link_config = LinkConfig.load(self.config.backend_json_path if self.config.backend_json_path.is_file() else None, app=APP_ID)
        preferred = (self.db.get_setting("model", "") or "").strip()
        if preferred:
            llm = dataclasses.replace(link_config.capability("llm"), model=preferred)
            link_config = dataclasses.replace(link_config, capabilities={**link_config.capabilities, "llm": llm})
        self._link = Link(link_config)
        return self._link.sync

    def tools(self) -> ff.Tools:
        if self._tools is None:
            self._tools = ff.discover(self.config.ffmpeg, self.config.ffprobe)
        return self._tools

    def hwdec_enabled(self) -> bool:
        value = self.db.get_setting("hwdec", "auto") or "auto"
        if value == "off":
            return False
        if value == "on":
            return True
        return self.config.encoder != "x264" and self.tools().nvenc_works()

    # ------------------------------------------------------------ events
    def emit(self, type_: str, data: dict[str, Any]) -> None:
        try:
            if self._emit is not None:
                self._emit(type_, data)
            else:
                family.emit(type_, data)
        except Exception:  # noqa: BLE001
            pass

    def _job_done(self, job: dict[str, Any]) -> None:
        if job["kind"] == "prepare" and job["state"] == "done" and self.db.get_setting("auto_transcribe", "off") == "on" and job.get("media_id"):
            info = media_store.lookup(self, job["media_id"])
            if info and info["has_audio"] and info["kind"] != "image":
                try:
                    analyze.schedule(self, job["media_id"], ["transcript"])
                except LumiereError:
                    pass
        if job["state"] == "failed":
            self.emit("lumiere.job.failed", {"id": job["id"], "kind": job["kind"], "error": clip(job["error"], 160)})

    # ------------------------------------------------------------ settings
    def get_settings(self) -> dict[str, Any]:
        out = {k: (self.db.get_setting(k, v) or v) for k, v in SETTINGS.items()}
        out["file_roots"] = [str(p) for p in self.config.file_roots]
        out["encoder"] = self.config.encoder
        out["render_workers"] = self.config.render_workers
        return out

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        unknown = set(patch) - set(SETTINGS)
        if unknown:
            raise LumiereError(f"Unknown settings: {', '.join(sorted(unknown))}.")
        choices = {"whisper_device": ("auto", "cuda", "cpu"), "hwdec": ("auto", "on", "off"), "auto_transcribe": ("on", "off"), "face_detector": faces.CHOICES,
                   "default_export": tuple(runner.EXPORTS)}
        for key, value in patch.items():
            value = "" if value is None else str(value).strip()
            if key in choices and value not in choices[key]:
                raise LumiereError(f"{key} must be one of {', '.join(choices[key])}.")
            if key == "export_folder" and value:
                folder = Path(value).expanduser()
                if not folder.is_dir():
                    raise LumiereError(f"The folder {folder} does not exist.")
                media_store._check_root(self, folder)
            self.db.set_setting(key, value)
        if "model" in patch and self._injected_link is None:
            if self._link is not None:
                try:
                    self.link_sync.close()
                except Exception:  # noqa: BLE001
                    pass
            self.link_sync = self._build_link()
        return self.get_settings()

    # ------------------------------------------------------------ status
    def counts(self) -> dict[str, int]:
        one = lambda sql: self.db.one(sql)["c"]  # noqa: E731
        return {"media": one("SELECT COUNT(*) c FROM media"), "projects": one("SELECT COUNT(*) c FROM projects"),
                "renders": one("SELECT COUNT(*) c FROM renders"), "active_jobs": one("SELECT COUNT(*) c FROM jobs WHERE state IN ('queued','running')")}

    def status(self) -> dict[str, Any]:
        from .analysis import speech

        try:
            model = self.link_sync.status()
        except Exception as error:  # noqa: BLE001
            model = {"error": f"{type(error).__name__}: {error}"}
        try:
            t = self.tools()
            ffinfo = {"ffmpeg": t.ffmpeg, "version": t.version, "nvenc": t.nvenc_works(), "vidstab": t.has_filter("vidstabdetect"),
                      "libass": t.has_filter("ass"), "hwdec": self.hwdec_enabled()}
        except LumiereError as error:
            ffinfo = {"error": str(error)}
        return {"service": SERVICE, "version": __version__, "counts": self.counts(), "model": model, "ffmpeg": ffinfo,
                "speech": speech.engine_status(), "speakers": speakers_mod.status(),
                "faces": faces.status(self.config.models_dir, prefer=self.db.get_setting("face_detector", "auto") or "auto"),
                "family": family.status(), "uptime_s": int(time.time() - self.started_at),
                "data_dir": str(self.config.data_dir) if self.config.data_dir_configured else "data", "schema": self.db.schema_version()}

    # ------------------------------------------------------------ renders
    def start_render(self, project_id: str, *, preset: str = "final", start: Any = None, end: Any = None, filename: str = "",
                     folder: str = "", lufs: Any = "default", subtitles: bool = False, mode: str = "render") -> dict[str, Any]:
        from . import projects as project_store
        from .util import parse_time

        project_store.doc(self, project_id)
        if mode == "copy":
            return self.jobs.submit("copy_cut", {"project": project_id, "filename": filename, "folder": folder}, label="Corte sin recodificar",
                                    project_id=project_id, dedupe=False)
        if preset not in runner.EXPORTS:
            raise LumiereError(f"Unknown export preset {preset!r}. Known: {', '.join(runner.EXPORTS)}.")
        folder = folder or self.db.get_setting("export_folder", "") or ""
        if folder:
            media_store._check_root(self, Path(folder))
            if not Path(folder).expanduser().is_dir():
                raise LumiereError(f"The folder {folder} does not exist.")
        params: dict[str, Any] = {"project": project_id, "preset": preset, "filename": filename, "folder": folder, "subtitles": subtitles}
        if start is not None:
            params["start"] = parse_time(start) if isinstance(start, str) else int(start)
        if end is not None:
            params["end"] = parse_time(end) if isinstance(end, str) else int(end)
        if lufs != "default":
            if lufs is not None and not -40 <= float(lufs) <= -5:
                raise LumiereError("lufs must be between -40 and -5, or null to leave the loudness alone.")
            params["lufs"] = None if lufs is None else float(lufs)
        label = f"Exportar {runner.EXPORTS[preset]['label']}"
        return self.jobs.submit("render", params, label=label, project_id=project_id, dedupe=False)

    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.config.port}" if self.config.port else ""
