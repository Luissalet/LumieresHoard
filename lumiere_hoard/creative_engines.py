"""Local EffectCraft/FilmCraft MCP processes and persisted editable projects.

The apps remain the editing engines. This adapter owns only portable discovery,
isolated app data, project folders, artifact metadata and safe file boundaries.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ENGINES = ("effectcraft", "filmcraft")
_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_LOCK = threading.RLock()


class CreativeEngineError(ValueError):
    """Portable configuration, schema, path, or engine invocation error."""


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


class CreativeEngines:
    def __init__(self, data_dir: Path, port: int = 5198):
        self.data_dir = Path(data_dir).resolve()
        self.root = self.data_dir / "creative"
        self.projects_dir = self.root / "projects"
        self.runtime_dir = self.root / "runtime"
        self.config_path = self.data_dir / "creative-engines.json"
        self.audit_path = self.root / "audit.jsonl"
        self.port = int(port)
        for path in (self.projects_dir, self.runtime_dir):
            path.mkdir(parents=True, exist_ok=True)

    def _config(self) -> dict[str, str]:
        if not self.config_path.exists():
            return {}
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CreativeEngineError(f"Cannot read {self.config_path}: {exc}") from None
        if not isinstance(data, dict) or set(data) - set(ENGINES) or any(not isinstance(v, str) for v in data.values()):
            raise CreativeEngineError(f"{self.config_path} must map only {', '.join(ENGINES)} to executable paths")
        return data

    def executable(self, engine: str) -> Path | None:
        self._validate_engine(engine)
        config = self._config()
        raw = config.get(engine) or os.environ.get(f"LUMIERE_{engine.upper()}_CLI")
        if raw:
            path = Path(raw).expanduser()
            return path.resolve() if path.is_file() else None
        name = f"{engine}-cli.exe" if os.name == "nt" else f"{engine}-cli"
        found = shutil.which(name)
        if found:
            return Path(found).resolve()
        roots = [self.data_dir / "creative-apps", self.data_dir / "craft-apps"]
        roots.extend(Path(p).expanduser() for p in os.environ.get("LUMIERE_CRAFT_BUNDLES", "").split(os.pathsep) if p.strip())
        for root in roots:
            direct = root / name
            if direct.is_file():
                return direct.resolve()
            if root.is_dir():
                matches = sorted(root.glob(f"{engine}-*-windows-x64-portable/{name}"))
                if not matches:
                    matches = sorted(root.glob(f"*/{name}"))
                if matches:
                    return matches[0].resolve()
        return None

    def status(self) -> dict[str, Any]:
        return {"engines": {
            engine: {"available": bool(self.executable(engine)),
                     "executable": str(self.executable(engine)) if self.executable(engine) else None,
                     "release": {"effectcraft": "0.3.1", "filmcraft": "0.2.1"}[engine],
                     "expected_tools": {"effectcraft": 21, "filmcraft": 17}[engine]}
            for engine in ENGINES
        }, "projects_dir": str(self.projects_dir)}

    @staticmethod
    def _validate_engine(engine: str) -> None:
        if engine not in ENGINES:
            raise CreativeEngineError(f"engine must be one of: {', '.join(ENGINES)}")

    def _project_dir(self, creative_id: str) -> Path:
        if not isinstance(creative_id, str) or not _ID_RE.fullmatch(creative_id):
            raise CreativeEngineError("creative_id must be a 32-character lowercase hexadecimal id")
        path = self.projects_dir / creative_id
        if not _inside(path, self.projects_dir):
            raise CreativeEngineError("creative project path is outside the local project store")
        return path

    def _manifest_path(self, creative_id: str) -> Path:
        return self._project_dir(creative_id) / "manifest.json"

    def get(self, creative_id: str) -> dict[str, Any]:
        path = self._manifest_path(creative_id)
        if not path.is_file():
            raise CreativeEngineError(f"No creative project {creative_id}.")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CreativeEngineError(f"Cannot read creative project manifest: {exc}") from None

    def _save_manifest(self, manifest: dict[str, Any]) -> None:
        path = self._manifest_path(manifest["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _runtime(self, engine: str, project_dir: Path) -> tuple[Path, list[str], dict[str, str]]:
        exe = self.executable(engine)
        if exe is None:
            raise CreativeEngineError(f"{engine} CLI unavailable; configure {self.config_path} or LUMIERE_{engine.upper()}_CLI")
        env = dict(os.environ)
        local = self.runtime_dir / engine
        for key in ("APPDATA", "LOCALAPPDATA"):
            value = local / key.lower()
            value.mkdir(parents=True, exist_ok=True)
            env[key] = str(value)
        if engine == "effectcraft":
            args = ["--empty", "mcp"]
        else:
            film_data = local / "data"
            film_data.mkdir(parents=True, exist_ok=True)
            args = ["--data-dir", str(film_data), "mcp"]
        return exe, args, env

    def _guard_paths(self, engine: str, calls: list[dict[str, Any]], folder: Path) -> None:
        def visit(value: Any, key: str = "") -> None:
            if isinstance(value, dict):
                for k, child in value.items():
                    visit(child, str(k).lower())
            elif isinstance(value, list):
                for child in value:
                    visit(child, key)
            elif isinstance(value, str) and any(token in key for token in ("path", "file", "folder", "dir")):
                candidate = Path(value).expanduser()
                if candidate.is_absolute():
                    resolved = candidate.resolve()
                else:
                    if ".." in candidate.parts:
                        raise CreativeEngineError("relative creative-engine paths cannot contain '..'")
                    resolved = (folder / candidate).resolve()
                if not _inside(resolved, folder):
                    raise CreativeEngineError(f"{engine} file paths must remain inside this creative project folder")

        for call in calls:
            visit(call.get("arguments", {}))
            if engine == "filmcraft" and call.get("tool") == "media_import":
                text = str(call.get("arguments", {}).get("text", ""))
                for raw in text.splitlines():
                    item = Path(raw.strip().strip('"')).expanduser()
                    if raw.strip() and (not item.is_absolute() or not _inside(item, folder)):
                        raise CreativeEngineError("FilmCraft media_import only accepts copies inside this creative project folder")

    async def _request(self, engine: str, project_dir: Path, calls: list[dict[str, Any]], *, open_saved: bool = False) -> list[dict[str, Any]]:
        exe, args, env = self._runtime(engine, project_dir)
        native = {"effectcraft": project_dir / f"{project_dir.name}.ecproj", "filmcraft": project_dir / f"{project_dir.name}.fcproj"}[engine]
        log_path = project_dir / "engine-stderr.log"
        output: list[dict[str, Any]] = []
        with log_path.open("a", encoding="utf-8") as stderr:
            params = StdioServerParameters(command=str(exe), args=args, env=env, cwd=str(project_dir), encoding="utf-8")
            async with stdio_client(params, errlog=stderr) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await asyncio.wait_for(session.initialize(), 45)
                    if calls and calls[0].get("tool") == "__list_tools__":
                        result = await asyncio.wait_for(session.list_tools(), 45)
                        return [{"tools": [_jsonable(x) for x in result.tools]}]
                    if open_saved:
                        if not native.is_file():
                            raise CreativeEngineError(f"Native project file is missing: {native.name}")
                        if engine == "effectcraft":
                            opened = await asyncio.wait_for(session.call_tool("open_project", {"path": str(native)}), 120)
                            output.append({"tool": "open_project", "is_error": bool(opened.isError), "content": [_jsonable(c) for c in opened.content]})
                        else:
                            opened = await asyncio.wait_for(session.call_tool("command_run", {"id": "file.open", "params": {"path": str(native)}}), 120)
                            output.append({"tool": "command_run:file.open", "is_error": bool(opened.isError), "content": [_jsonable(c) for c in opened.content]})
                        if opened.isError:
                            return output
                    for i, call in enumerate(calls, 1):
                        result = await asyncio.wait_for(session.call_tool(call["tool"], call.get("arguments", {})), 180)
                        blocks: list[dict[str, Any]] = []
                        for content in result.content:
                            if getattr(content, "type", None) == "image" and getattr(content, "data", None):
                                preview = project_dir / f"call-{i:02d}.png"
                                preview.write_bytes(base64.b64decode(content.data))
                                blocks.append({"type": "image", "path": str(preview), "mimeType": content.mimeType})
                            else:
                                blocks.append(_jsonable(content))
                        output.append({"tool": call["tool"], "is_error": bool(result.isError), "content": blocks})
                        if result.isError:
                            return output
                    if open_saved:
                        if engine == "effectcraft":
                            saved = await asyncio.wait_for(session.call_tool("save_project", {"path": str(native)}), 180)
                            output.append({"tool": "save_project", "is_error": bool(saved.isError), "content": [_jsonable(c) for c in saved.content]})
                        else:
                            saved = await asyncio.wait_for(session.call_tool("command_run", {"id": "file.saveAs", "params": {"path": str(native)}}), 180)
                            output.append({"tool": "command_run:file.saveAs", "is_error": bool(saved.isError), "content": [_jsonable(c) for c in saved.content]})
        return output

    def tools(self, engine: str) -> dict[str, Any]:
        self._validate_engine(engine)
        temporary = self.root / "schema-probe" / engine
        temporary.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            result = asyncio.run(self._request(engine, temporary, [{"tool": "__list_tools__"}]))[0]
        return {"engine": engine, "count": len(result["tools"]), "tools": result["tools"]}

    @staticmethod
    def _validate_calls(engine: str, calls: list[dict[str, Any]]) -> None:
        if not isinstance(calls, list) or not calls or len(calls) > 32:
            raise CreativeEngineError("calls must contain 1 to 32 native tool call objects")
        for call in calls:
            if not isinstance(call, dict) or not isinstance(call.get("tool"), str) or call["tool"].startswith("__"):
                raise CreativeEngineError("each call must have a public native tool name")
            if not isinstance(call.get("arguments", {}), dict):
                raise CreativeEngineError("native tool arguments must be an object")
        if engine == "effectcraft" and any(c["tool"] == "run_script" for c in calls):
            # The upstream host confines script file access to the project folder.
            pass

    def _audit(self, entry: dict[str, Any]) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, self.audit_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def call(self, creative_id: str, calls: list[dict[str, Any]]) -> dict[str, Any]:
        manifest = self.get(creative_id)
        engine = manifest["engine"]
        self._validate_calls(engine, calls)
        folder = self._project_dir(creative_id)
        self._guard_paths(engine, calls, folder)
        start = time.perf_counter()
        with _LOCK:
            result = asyncio.run(self._request(engine, folder, calls, open_saved=True))
        failed = any(x["is_error"] for x in result)
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        manifest["last_tools"] = [c["tool"] for c in calls]
        manifest["last_error"] = next((x["content"][0].get("text", "engine error") for x in result if x["is_error"] and x["content"]), None)
        self._save_manifest(manifest)
        self._audit({"creative_id": creative_id, "engine": engine, "tools": manifest["last_tools"],
                     "ok": not failed, "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                     "ts": manifest["updated_at"]})
        return {"project": manifest, "calls": result, "ok": not failed}

    def _begin(self, engine: str, project_id: str | None) -> dict[str, Any]:
        self._validate_engine(engine)
        if not self.executable(engine):
            raise CreativeEngineError(f"{engine} is not configured")
        if project_id is not None and not re.fullmatch(r"prj_[0-9abcdefghjkmnpqrstvwxyz]{8}", project_id):
            raise CreativeEngineError("project_id must be a Lumiere project id")
        creative_id = uuid.uuid4().hex
        folder = self._project_dir(creative_id)
        folder.mkdir(parents=True, exist_ok=False)
        return {"id": creative_id, "engine": engine, "project_id": project_id,
                "created_at": datetime.now(timezone.utc).isoformat(), "project_dir": str(folder),
                "native_path": str(folder / f"{creative_id}.{ 'ecproj' if engine == 'effectcraft' else 'fcproj'}"),
                "preview_path": str(folder / "preview.png"), "render_path": None,
                "state": "creating", "last_tools": [], "last_error": None}

    def _finish(self, manifest: dict[str, Any], calls: list[dict[str, Any]], *, render_path: str | None = None) -> dict[str, Any]:
        folder = self._project_dir(manifest["id"])
        manifest["last_tools"] = [c["tool"] if "tool" in c else c.get("id", "") for c in calls]
        manifest["state"] = "complete"
        manifest["render_path"] = render_path
        self._save_manifest(manifest)
        self._audit({"creative_id": manifest["id"], "engine": manifest["engine"], "tools": manifest["last_tools"],
                     "ok": True, "ts": manifest["created_at"]})
        return {**manifest, "project_url": f"/api/creative/{manifest['id']}/project",
                "preview_url": f"/api/creative/{manifest['id']}/preview",
                "render_url": f"/api/creative/{manifest['id']}/render" if render_path else None,
                "media_receive_url": f"http://127.0.0.1:{self.port}/api/creative/{manifest['id']}/render" if render_path else None}

    def create_title_card(self, *, text: str, width: int = 1280, height: int = 720, fps: float = 24,
                          duration: float = 3, project_id: str | None = None) -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip() or len(text) > 300:
            raise CreativeEngineError("text must contain 1 to 300 characters")
        if not 16 <= width <= 8192 or not 16 <= height <= 8192 or not 1 <= fps <= 120 or not 0.5 <= duration <= 30:
            raise CreativeEngineError("canvas must be 16–8192 px, frame rate 1–120, and duration 0.5–30 s")
        manifest = self._begin("effectcraft", project_id)
        folder = self._project_dir(manifest["id"])
        p = folder / f"{manifest['id']}.ecproj"
        preview = folder / "preview.png"
        calls = [
            {"tool": "execute_command", "arguments": {"command": "comp.new", "params": {"name": text[:60], "width": width, "height": height, "frameRate": fps, "duration": duration, "background": "#17212b"}}},
            {"tool": "execute_command", "arguments": {"command": "layer.newText", "params": {"name": "Title", "text": text, "position": [width / 2, height / 2], "box": [width * 0.08, height * 0.32, width * 0.84, height * 0.36], "justify": "center", "size": max(18, min(96, int(height * 0.12))), "fill": "#ffffff"}}},
        ]
        start = time.perf_counter()
        with _LOCK:
            exe, args, env = self._runtime("effectcraft", folder)
            with (folder / "engine-stderr.log").open("a", encoding="utf-8") as stderr:
                params = StdioServerParameters(command=str(exe), args=args, env=env, cwd=str(folder), encoding="utf-8")
                async def workflow():
                    async with stdio_client(params, errlog=stderr) as (reader, writer):
                        async with ClientSession(reader, writer) as session:
                            await asyncio.wait_for(session.initialize(), 45)
                            raw: list[dict[str, Any]] = []
                            for call in calls:
                                result = await asyncio.wait_for(session.call_tool(call["tool"], call["arguments"]), 180)
                                raw.append({"tool": call["tool"], "is_error": bool(result.isError), "content": [_jsonable(c) for c in result.content]})
                                if result.isError:
                                    return raw, [], None
                            try:
                                layer_id = json.loads(raw[1]["content"][0]["text"]).get("layer")
                            except (IndexError, KeyError, TypeError, json.JSONDecodeError):
                                return raw, [], None
                            if layer_id is None:
                                return raw + [{"tool": "layer.newText", "is_error": True, "content": [{"type": "text", "text": "EffectCraft did not return the created title layer id"}]}], [], None
                            extra = [
                                {"tool": "add_keyframe", "arguments": {"layer": layer_id, "path": "transform/opacity", "keys": [
                                    {"time": 0, "value": 0}, {"time": 0.35, "value": 100},
                                    {"time": max(0.4, duration - 0.35), "value": 100}, {"time": duration, "value": 0}], "interpolation": "linear"}},
                                {"tool": "save_project", "arguments": {"path": str(p)}},
                                {"tool": "render_frame", "arguments": {"time": min(0.75, duration / 2), "path": str(preview), "inline": False, "max_side": max(width, height)}},
                                {"tool": "get_property", "arguments": {"layer": layer_id, "path": "transform/opacity"}},
                            ]
                            tail: list[dict[str, Any]] = []
                            for call in extra:
                                result = await asyncio.wait_for(session.call_tool(call["tool"], call["arguments"]), 180)
                                tail.append({"tool": call["tool"], "is_error": bool(result.isError), "content": [_jsonable(c) for c in result.content]})
                                if result.isError:
                                    break
                            return raw, tail, layer_id
                raw, tail, text_layer_id = asyncio.run(workflow())
            if any(x["is_error"] for x in raw):
                manifest["state"] = "failed"
                manifest["last_error"] = "EffectCraft could not create the title composition"
                self._save_manifest(manifest)
                self._audit({"creative_id": manifest["id"], "engine": "effectcraft", "ok": False,
                             "duration_ms": round((time.perf_counter() - start) * 1000, 1), "ts": manifest["created_at"]})
                raise CreativeEngineError(manifest["last_error"])
        final_calls = raw + tail
        if any(x["is_error"] for x in tail) or not p.is_file() or not preview.is_file():
            manifest["state"] = "failed"
            manifest["last_error"] = "EffectCraft failed to save the editable title project or render its preview"
            self._save_manifest(manifest)
            raise CreativeEngineError(manifest["last_error"])
        manifest.update({"native_path": str(p), "preview_path": str(preview), "title": text, "width": width,
                         "height": height, "fps": fps, "duration_seconds": duration, "text_layer_id": text_layer_id,
                         "render_path": None, "editable": True})
        result = self._finish(manifest, final_calls)
        result["calls"] = final_calls
        result["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 1)
        return result

    def render_title_video(self, creative_id: str) -> dict[str, Any]:
        """Render the saved active EffectCraft composition with its native H.264 encoder."""
        manifest = self.get(creative_id)
        started = time.perf_counter()

        def fail(message: str) -> CreativeEngineError:
            manifest["render_state"] = "failed"
            manifest["last_error"] = message
            manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save_manifest(manifest)
            self._audit({"creative_id": creative_id, "engine": "effectcraft", "tool": "render", "ok": False,
                         "duration_ms": round((time.perf_counter() - started) * 1000, 1), "ts": manifest["updated_at"]})
            return CreativeEngineError(message)

        if manifest.get("engine") != "effectcraft":
            raise CreativeEngineError("animated title rendering requires an EffectCraft project")
        folder = self._project_dir(creative_id)
        native = Path(manifest.get("native_path", "")).resolve()
        if not _inside(native, folder) or native.suffix.lower() != ".ecproj" or not native.is_file():
            raise fail("EffectCraft project file is missing or outside its creative project folder")
        ffprobe = os.environ.get("LUMIERE_FFPROBE") or shutil.which("ffprobe")
        if not ffprobe or not Path(ffprobe).is_file():
            raise fail("ffprobe is required to verify the native MP4 frame rate and duration; configure LUMIERE_FFPROBE")

        try:
            exe, _, env = self._runtime("effectcraft", folder)
        except CreativeEngineError as exc:
            raise fail(str(exc)) from None
        for key in ("APPDATA", "LOCALAPPDATA"):
            target = self.runtime_dir / "effectcraft" / key.lower()
            target.mkdir(parents=True, exist_ok=True)
            env[key] = str(target)

        # Read the active composition so that the verification matches the saved
        # project even if a native MCP edit changed its duration or frame rate.
        info_cmd = [str(exe), "info", "--project", str(native), "--json"]
        try:
            info = subprocess.run(info_cmd, cwd=str(folder), env=env, capture_output=True, text=True,
                                  timeout=60, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise fail(f"EffectCraft project inspection failed: {exc}") from None
        info_text = info.stdout.strip()
        log_path = folder / "render-cli.log"
        with log_path.open("a", encoding="utf-8") as log:
            log.write(json.dumps({"command": info_cmd, "returncode": info.returncode,
                                  "stdout": info.stdout, "stderr": info.stderr}, ensure_ascii=False) + "\n")
        if info.returncode != 0:
            raise fail(f"EffectCraft could not inspect the saved project: {(info.stderr or info_text)[-1200:]}")
        try:
            project_info = json.loads(info_text)
            comp = project_info["activeComp"]
            expected_fps = float(comp["frameRate"])
            expected_duration = float(comp["duration"])
            expected_width = int(comp["width"])
            expected_height = int(comp["height"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            raise fail("EffectCraft info did not report the active composition's dimensions, fps and duration") from None
        if expected_fps <= 0 or expected_duration <= 0 or expected_width <= 0 or expected_height <= 0:
            raise fail("EffectCraft reported invalid active composition settings")

        render = folder / f"render-{uuid.uuid4().hex[:8]}.mp4"
        render_cmd = [str(exe), "render", "--project", str(native), "--out", str(render),
                      "--format", "h264", "--quality", "best", "--audio", "off", "--json"]
        # Native rendering writes frames directly into the MP4. No frame sequence
        # is retained in Python memory or on disk.
        timeout = max(120, min(1800, int(expected_duration * expected_fps * 5)))
        manifest["render_state"] = "rendering"
        manifest["last_error"] = None
        self._save_manifest(manifest)
        phase = "native H.264 render"
        try:
            try:
                result = subprocess.run(render_cmd, cwd=str(folder), env=env, capture_output=True, text=True,
                                        timeout=timeout, check=False)
            except OSError as exc:
                raise CreativeEngineError(f"Could not start EffectCraft H.264 render: {exc}") from None
            with log_path.open("a", encoding="utf-8") as log:
                log.write(json.dumps({"command": render_cmd, "returncode": result.returncode,
                                      "stdout": result.stdout, "stderr": result.stderr}, ensure_ascii=False) + "\n")
            if result.returncode != 0 or not render.is_file() or render.stat().st_size < 512:
                detail = (result.stderr or result.stdout or f"exit code {result.returncode}")[-1600:]
                raise CreativeEngineError(f"EffectCraft H.264 render failed: {detail}")

            phase = "MP4 verification"
            try:
                probe = subprocess.run([str(ffprobe), "-v", "error", "-count_frames", "-show_entries",
                                        "format=duration:stream=codec_name,width,height,avg_frame_rate,nb_read_frames",
                                        "-of", "json", str(render)], cwd=str(folder), env=env, capture_output=True,
                                       text=True, timeout=60, check=False)
            except OSError as exc:
                raise CreativeEngineError(f"Could not start ffprobe verification: {exc}") from None
            if probe.returncode != 0:
                raise CreativeEngineError(f"ffprobe could not verify the rendered MP4: {(probe.stderr or probe.stdout)[-1200:]}")
            try:
                metadata = json.loads(probe.stdout)
                video = next(stream for stream in metadata["streams"] if stream.get("codec_name") == "h264")
                actual_fps = self._parse_rate(video["avg_frame_rate"])
                actual_duration = float(metadata["format"]["duration"])
                frame_count = int(video["nb_read_frames"])
                actual_width = int(video["width"])
                actual_height = int(video["height"])
            except (json.JSONDecodeError, KeyError, StopIteration, TypeError, ValueError, ZeroDivisionError):
                raise CreativeEngineError("ffprobe did not report a valid H.264 stream, frame rate, frame count and duration") from None
            if (actual_width != expected_width or actual_height != expected_height or
                    abs(actual_fps - expected_fps) > 0.01 or
                    abs(actual_duration - expected_duration) > max(0.05, 1.0 / expected_fps) or
                    abs(frame_count - round(expected_duration * expected_fps)) > 1):
                raise CreativeEngineError(
                    "Rendered MP4 settings do not match the saved composition "
                    f"(expected {expected_width}x{expected_height} at {expected_fps:g} fps for {expected_duration:g}s; "
                    f"got {actual_width}x{actual_height} at {actual_fps:g} fps for {actual_duration:g}s/{frame_count} frames)"
                )
        except subprocess.TimeoutExpired as exc:
            detail = f"during {phase} after {exc.timeout or timeout}s"
            with log_path.open("a", encoding="utf-8") as log:
                log.write(json.dumps({"command": render_cmd, "error": "timeout", "detail": detail}) + "\n")
            raise fail(f"EffectCraft {detail}") from None
        except CreativeEngineError as exc:
            if manifest.get("last_error") != str(exc):
                raise fail(str(exc)) from None
            raise

        now = datetime.now(timezone.utc).isoformat()
        manifest.update({"render_state": "complete", "render_path": str(render), "render_codec": "h264",
                         "render_width": expected_width, "render_height": expected_height,
                         "render_fps": actual_fps, "render_duration_seconds": actual_duration,
                         "render_frame_count": frame_count, "render_verified_by": str(ffprobe),
                         "rendered_at": now, "last_error": None, "updated_at": now})
        self._save_manifest(manifest)
        self._audit({"creative_id": creative_id, "engine": "effectcraft", "tool": "render", "ok": True,
                     "duration_ms": round((time.perf_counter() - started) * 1000, 1), "ts": now})
        return {**manifest, "project_url": f"/api/creative/{creative_id}/project",
                "preview_url": f"/api/creative/{creative_id}/preview",
                "render_url": f"/api/creative/{creative_id}/render",
                "media_receive_url": f"http://127.0.0.1:{self.port}/api/creative/{creative_id}/render"}

    @staticmethod
    def _parse_rate(value: str) -> float:
        numerator, denominator = value.split("/", 1)
        divisor = float(denominator)
        if divisor == 0:
            raise ZeroDivisionError
        return float(numerator) / divisor

    def create_film_sequence(self, source: Path, *, source_media_id: str, width: int, height: int, fps: float,
                             project_id: str | None = None) -> dict[str, Any]:
        if not source.is_file():
            raise CreativeEngineError("source media is missing")
        if not 16 <= width <= 8192 or not 16 <= height <= 8192 or not 1 <= fps <= 120:
            raise CreativeEngineError("sequence canvas must be 16–8192 px at 1–120 fps")
        manifest = self._begin("filmcraft", project_id)
        folder = self._project_dir(manifest["id"])
        media_dir = folder / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        ext = source.suffix.lower()
        if len(ext) > 10 or not re.fullmatch(r"\.[a-z0-9]{1,9}", ext):
            ext = ".mp4"
        source_copy = media_dir / f"source-{source_media_id}{ext}"
        shutil.copy2(source, source_copy)
        if source.resolve() == source_copy.resolve():
            raise CreativeEngineError("source copy must be separate from the original")
        proj = folder / f"{manifest['id']}.fcproj"
        render = folder / "render.mp4"
        preview = folder / "preview.png"
        calls = [
            {"tool": "media_import", "arguments": {"text": str(source_copy)}},
        ]
        start = time.perf_counter()
        with _LOCK:
            exe, args, env = self._runtime("filmcraft", folder)
            with (folder / "engine-stderr.log").open("a", encoding="utf-8") as stderr:
                params = StdioServerParameters(command=str(exe), args=args, env=env, cwd=str(folder), encoding="utf-8")
                async def workflow():
                    async with stdio_client(params, errlog=stderr) as (reader, writer):
                        async with ClientSession(reader, writer) as session:
                            await asyncio.wait_for(session.initialize(), 45)
                            out: list[dict[str, Any]] = []
                            imported = await asyncio.wait_for(session.call_tool("media_import", calls[0]["arguments"]), 180)
                            out.append({"tool": "media_import", "is_error": bool(imported.isError), "content": [_jsonable(c) for c in imported.content]})
                            if imported.isError:
                                return out
                            try:
                                imported_json = json.loads(imported.content[0].text)
                                item_id = imported_json["items"][0]
                            except (IndexError, KeyError, TypeError, json.JSONDecodeError):
                                return out + [{"tool": "media_import", "is_error": True, "content": [{"type": "text", "text": "FilmCraft import did not return a media item id"}]}]
                            commands = [
                                ("file.newSequence", {"name": f"Lumiere composition {manifest['id'][:8]}", "fromItem": item_id,
                                                       "width": width, "height": height, "fps": fps}),
                                ("file.saveAs", {"path": str(proj)}),
                                ("file.exportMedia", {"path": str(render), "format": "h264", "width": width, "height": height,
                                                      "fps": fps, "wait": True}),
                            ]
                            for command, parameters in commands:
                                result = await asyncio.wait_for(session.call_tool("command_run", {"id": command, "params": parameters}), 300)
                                out.append({"tool": f"command_run:{command}", "is_error": bool(result.isError), "content": [_jsonable(c) for c in result.content]})
                                if result.isError:
                                    return out
                            sequence = await asyncio.wait_for(session.call_tool("sequence_inspect", {}), 60)
                            out.append({"tool": "sequence_inspect", "is_error": bool(sequence.isError), "content": [_jsonable(c) for c in sequence.content]})
                            frame = await asyncio.wait_for(session.call_tool("render_frame", {"seconds": 0, "max_side": max(width, height)}), 120)
                            frame_blocks = []
                            for content in frame.content:
                                if getattr(content, "type", None) == "image" and getattr(content, "data", None):
                                    preview.write_bytes(base64.b64decode(content.data))
                                    frame_blocks.append({"type": "image", "path": str(preview), "mimeType": content.mimeType})
                                else:
                                    frame_blocks.append(_jsonable(content))
                            out.append({"tool": "render_frame", "is_error": bool(frame.isError), "content": frame_blocks})
                            return out
                final_calls = asyncio.run(workflow())
        if any(x["is_error"] for x in final_calls) or not proj.is_file() or not render.is_file():
            manifest["state"] = "failed"
            manifest["last_error"] = "FilmCraft failed to import, sequence, save, or export the copied source"
            manifest["source_copy"] = str(source_copy)
            self._save_manifest(manifest)
            self._audit({"creative_id": manifest["id"], "engine": "filmcraft", "tools": [x["tool"] for x in final_calls],
                         "ok": False, "duration_ms": round((time.perf_counter() - start) * 1000, 1), "ts": manifest["created_at"]})
            raise CreativeEngineError(manifest["last_error"])
        manifest.update({"native_path": str(proj), "preview_path": str(preview) if preview.exists() else None,
                         "render_path": str(render), "source_copy": str(source_copy), "source_media_id": source_media_id,
                         "width": width, "height": height, "fps": fps, "editable": True})
        result = self._finish(manifest, final_calls, render_path=str(render))
        result["calls"] = final_calls
        result["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 1)
        return result
