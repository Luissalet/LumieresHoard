"""Compare the editor's accelerated (WebGL) preview with the backend's exact frame, case by case.

For a set of synthetic projects (transitions, colour effects, transforms with keyframes, fit modes, crop, fades) it opens the
editor in headless Chromium, seeks the playhead, reads the preview canvas back and measures the mean absolute difference
against ``/api/projects/{id}/frame`` (the picture the export draws) for the same moment. Transitions, fades and the colour effects are also
compared with a frame pulled out of a real export (the single-frame route clips out-of-range colours in its JPEG).

It is NOT part of the pytest suite (it needs a browser and takes a few minutes). Requirements: ffmpeg/ffprobe on the PATH,
``pip install playwright pillow`` and a Chromium for Playwright (``PLAYWRIGHT_BROWSERS_PATH`` may point at it).

    python scripts/preview_check.py                       # every case, prints a table
    python scripts/preview_check.py --only fx_,fit_       # cases whose name starts with one of these
    python scripts/preview_check.py --out /tmp/pc --keep  # keep side-by-side images and the data dir

Why the media are re-encoded: the test Chromium has no H.264, so each proxy is replaced by a VP9-in-MP4 copy (same 540p size,
same colour tags) before the page loads. The original files stay the render's source, exactly as in real use.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import requests
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TAGS = ["-colorspace", "smpte170m", "-color_primaries", "smpte170m", "-color_trc", "smpte170m", "-color_range", "tv"]
COMPARE_W = 640  # both pictures are produced (and compared) at this width
CHROMIUM_ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist",
                 "--autoplay-policy=no-user-gesture-required"]


# ------------------------------------------------------------------ environment

def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_media(d: Path) -> dict[str, Path]:
    """Synthetic sources tagged BT.601 (the colour matrix the proxies use), small and quick to make."""
    out = {name: d / name for name in ("a.mp4", "b.mp4", "v.mp4", "key.mp4", "pic.png", "grade.cube")}
    enc = ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-g", "15", *TAGS]
    ff("-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=8", *enc, str(out["a.mp4"]))
    ff("-f", "lavfi", "-i", "testsrc=s=1280x720:r=30:d=8", *enc, str(out["b.mp4"]))
    ff("-f", "lavfi", "-i", "testsrc2=s=720x1280:r=30:d=8", *enc, str(out["v.mp4"]))
    # a green screen with a red and a blue block and a darker green patch (keying should keep the blocks only)
    ff("-f", "lavfi", "-i", "color=c=0x00ff00:s=1280x720:r=30:d=8", "-vf",
       "drawbox=x=200:y=150:w=300:h=300:color=red:t=fill,drawbox=x=700:y=250:w=360:h=260:color=0x2050e0:t=fill,"
       "drawbox=x=560:y=40:w=120:h=90:color=0x00b000:t=fill", *enc, str(out["key.mp4"]))
    ff("-f", "lavfi", "-i", "testsrc2=s=800x600", "-frames:v", "1", str(out["pic.png"]))
    out["grade.cube"].write_text(_cube(), encoding="utf-8")
    return out


def _cube(size: int = 9) -> str:
    """A visible grade: red and blue swapped partly, green lifted (a 3D LUT with the red index varying fastest)."""
    rows = [f"TITLE \"check\"", f"LUT_3D_SIZE {size}"]
    n = size - 1
    for b in range(size):
        for g in range(size):
            for r in range(size):
                R, G, B = r / n, g / n, b / n
                rows.append(f"{0.7 * R + 0.3 * B:.5f} {min(1.0, G * 0.8 + 0.2):.5f} {0.7 * B + 0.3 * R:.5f}")
    return "\n".join(rows) + "\n"


class Server:
    def __init__(self, data: Path, port: int):
        env = {**os.environ, "LUMIERE_DATA_DIR": str(data), "LUMIERE_PORT": str(port), "PORT_STRICT": "1"}
        self.base = f"http://127.0.0.1:{port}"
        self.log = open(data.parent / "server.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen([sys.executable, "-m", "lumiere_hoard"], cwd=ROOT, env=env, stdout=self.log, stderr=subprocess.STDOUT)
        self.http = requests.Session()
        self.http.trust_env = False
        for _ in range(100):
            try:
                if self.http.get(self.base + "/api/health", timeout=1).ok:
                    return
            except requests.RequestException:
                time.sleep(0.3)
        raise RuntimeError("the app did not start")

    def get(self, path: str, **kw: Any) -> requests.Response:
        r = self.http.get(self.base + path, timeout=kw.pop("timeout", 120), **kw)
        r.raise_for_status()
        return r

    def post(self, path: str, body: dict[str, Any], timeout: int = 300) -> dict[str, Any]:
        r = self.http.post(self.base + path, json=body, timeout=timeout)
        if not r.ok:
            raise RuntimeError(f"{path}: {r.status_code} {r.text[:400]}")
        return r.json()

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def import_media(srv: Server, data: Path, files: dict[str, Path]) -> dict[str, str]:
    """Import everything, wait for the proxies, then swap each video proxy for a VP9-in-MP4 copy the test browser can play."""
    from lumiere_hoard.config import Config

    cache = Config(data_dir=data, port=0, data_dir_configured=True).cache_dir
    ids: dict[str, str] = {}
    for name, path in files.items():
        if path.suffix == ".cube":
            continue
        ids[name] = srv.post("/api/media/import", {"path": str(path)})["id"]
    for name, mid in ids.items():
        if name.endswith(".png"):
            continue
        for _ in range(2000):  # the machine may be busy: be patient
            if (cache / mid / "sprite.json").exists():
                break
            time.sleep(0.3)
        else:
            raise RuntimeError(f"proxy of {name} never finished")
        proxy = cache / mid / "proxy.mp4"
        tmp = cache / mid / "proxy.vp9.mp4"
        ff("-i", str(files[name]), "-vf", "scale=trunc(iw*540/min(iw\\,ih)/2)*2:trunc(ih*540/min(iw\\,ih)/2)*2", "-an", "-c:v", "libvpx-vp9", "-deadline",
           "realtime", "-cpu-used", "8", "-crf", "12", "-b:v", "0", "-g", "6", "-pix_fmt", "yuv420p", *TAGS, str(tmp))
        os.replace(tmp, proxy)
    return ids


# ------------------------------------------------------------------ projects

class Proj:
    """A project built through the same /edit route the UI and the assistants use."""

    def __init__(self, srv: Server, M: dict[str, str], name: str, preset: str = "hd720", background: Optional[str] = None):
        self.srv, self.M = srv, M
        self.id = srv.post("/api/projects", {"name": name, "preset": preset})["id"]
        if background:
            self.edit({"op": "canvas", "background": background})

    def edit(self, *ops: dict[str, Any]) -> list[dict[str, Any]]:
        return self.srv.post(f"/api/projects/{self.id}/edit", {"ops": list(ops)})["results"]

    def doc(self) -> dict[str, Any]:
        return self.srv.get(f"/api/projects/{self.id}").json()["doc"]

    def add(self, media: str, track: Optional[str] = None, **kw: Any) -> str:
        op = {"op": "add_media", "media": self.M[media], **kw}
        if track:
            op["track"] = track
        return self.edit(op)[0]["clip"]

    def overlay_track(self) -> str:
        return self.edit({"op": "track_add", "kind": "video", "name": "Overlay"})[0]["track"]

    def fx(self, clip: str, kind: str, **params: Any) -> None:
        self.edit({"op": "filter_add", "clips": [clip], "type": kind, "params": params})

    def tf(self, clip: str, **transform: Any) -> None:
        self.edit({"op": "set", "clip": clip, "props": {"transform": transform}})

    def keys(self, clip: str, prop: str, keys: list[tuple[int, float, str]]) -> None:
        self.edit({"op": "keyframes", "clip": clip, "prop": prop, "keys": [{"t": t, "v": v, "ease": e} for t, v, e in keys]})


@dataclass
class Case:
    name: str
    build: Callable[[Server, dict[str, str], Path], Proj]
    times: list[int]
    export: bool = False  # also compare with a frame of a real export
    gl_width: int = 0  # render the preview at this width (0 = COMPARE_W), then scale it down: noisy effects only match at the export's own size
    preset: str = "web"  # export preset for the reference frame (noise only survives a near-lossless one)
    frame: bool = True  # compare with /frame
    note: str = ""


def _fx_case(kind: str, media: str = "a.mp4", **params: Any) -> Case:
    def build(srv: Server, M: dict[str, str], files: Path) -> Proj:
        p = Proj(srv, M, f"fx_{kind}")
        c = p.add(media, src_in=0, src_out=3000)
        p.fx(c, kind, **({**params, "file": str(files / "grade.cube")} if kind == "lut" else params))
        return p

    return Case(f"fx_{kind}", build, [1500], export=True)


def _fit_case(fit: str, media: str, **tf: Any) -> Case:
    def build(srv: Server, M: dict[str, str], files: Path) -> Proj:
        p = Proj(srv, M, f"fit_{fit}")
        c = p.add(media, fit=fit)
        if tf:
            p.tf(c, **tf)
        return p

    suffix = "_focus" if "focus_x" in tf else ("_scaled" if tf else "")
    return Case(f"fit_{fit}_{media.split('.')[0]}{suffix}", build, [2000])


def transition_cases() -> list[Case]:
    from lumiere_hoard.timeline import TRANSITIONS

    cases = []
    for k, kind in enumerate(TRANSITIONS):
        def build(srv: Server, M: dict[str, str], files: Path, kind: str = kind) -> Proj:
            p = Proj(srv, M, "xfade_" + kind)
            p.add("a.mp4", src_in=0, src_out=3000)
            c = p.add("b.mp4", src_in=1000, src_out=4000)
            p.edit({"op": "transition", "clip": c, "type": kind, "dur": 1000})
            return p

        # the transition occupies 2000..3000 ms: one third and two thirds of the way through
        cases.append(Case(f"xfade_{kind}", build, [2330, 2670], export=True, gl_width=1280 if kind == "dissolve" else 0,
                          preset="master" if kind == "dissolve" else "web", frame=kind != "dissolve"))
    return cases


def all_cases() -> list[Case]:
    cases: list[Case] = []

    def plain(srv: Server, M: dict[str, str], files: Path) -> Proj:
        p = Proj(srv, M, "plain")
        p.add("a.mp4")
        return p

    cases.append(Case("base_plain", plain, [500, 3000]))

    def image(srv: Server, M: dict[str, str], files: Path) -> Proj:
        p = Proj(srv, M, "image")
        p.add("pic.png", length=3000)
        return p

    cases.append(Case("base_image", image, [1000]))
    cases += [_fit_case("contain", "v.mp4"), _fit_case("cover", "v.mp4"), _fit_case("fill", "v.mp4"), _fit_case("none", "v.mp4"),
              _fit_case("blur", "v.mp4"), _fit_case("cover", "v.mp4", focus_x=0.1, focus_y=0.8), _fit_case("blur", "a.mp4", scale=0.5)]

    def crop(srv: Server, M: dict[str, str], files: Path) -> Proj:
        p = Proj(srv, M, "crop")
        c = p.add("a.mp4")
        p.edit({"op": "set", "clip": c, "props": {"crop": {"left": 0.1, "top": 0.2, "right": 0.15, "bottom": 0.05}}})
        return p

    cases.append(Case("crop", crop, [2000]))

    for kind, params in [("eq", {"brightness": 0.1, "contrast": 1.3, "saturation": 1.4, "gamma": 1.2}), ("grayscale", {}), ("sepia", {}), ("vintage", {}),
                         ("warm", {"amount": 0.7}), ("cool", {"amount": 0.7}), ("contrast_pop", {"amount": 0.7}), ("vignette", {"strength": 0.7}),
                         ("blur", {"radius": 6}), ("sharpen", {"amount": 1.5}), ("pixelate", {"size": 16}), ("hflip", {}), ("vflip", {}), ("lut", {})]:
        cases.append(_fx_case(kind, **params))

    def chroma(srv: Server, M: dict[str, str], files: Path) -> Proj:
        p = Proj(srv, M, "chroma")
        p.add("b.mp4")
        top = p.overlay_track()
        c = p.add("key.mp4", track=top)
        p.fx(c, "chromakey", color="#00FF00", similarity=0.2, blend=0.08)
        return p

    cases.append(Case("fx_chromakey", chroma, [2000]))

    def overlay_static(srv: Server, M: dict[str, str], files: Path) -> Proj:
        p = Proj(srv, M, "tf_static")
        p.add("b.mp4")
        c = p.add("a.mp4", track=p.overlay_track())
        p.tf(c, scale=0.55, x=0.18, y=-0.12, rotation=15, opacity=0.8)
        return p

    cases.append(Case("tf_static", overlay_static, [2000]))

    def overlay_keys(srv: Server, M: dict[str, str], files: Path) -> Proj:
        p = Proj(srv, M, "tf_keys")
        p.add("b.mp4", src_in=0, src_out=4000)
        c = p.add("a.mp4", track=p.overlay_track(), src_in=0, src_out=4000)
        p.keys(c, "x", [(0, -0.3, "ease_in_out"), (2000, 0.3, "linear"), (4000, 0.0, "ease_out")])
        p.keys(c, "scale", [(0, 0.4, "ease_in"), (2000, 0.8, "hold"), (3000, 1.0, "linear")])
        p.keys(c, "rotation", [(0, -20, "linear"), (4000, 40, "ease_in_out")])
        p.keys(c, "opacity", [(0, 0.2, "linear"), (2000, 1.0, "ease_out"), (4000, 0.6, "linear")])
        return p

    cases.append(Case("tf_keyframes", overlay_keys, [500, 1500, 2500, 3500]))

    def fades(srv: Server, M: dict[str, str], files: Path) -> Proj:
        p = Proj(srv, M, "fades")
        p.add("a.mp4", src_in=0, src_out=4000)
        p.edit({"op": "set", "clip": p.doc()["tracks"][0]["clips"][0]["id"], "props": {"fade_in": 1000, "fade_out": 1000}})
        return p

    cases.append(Case("fade_in_out", fades, [500, 3500], export=True))
    cases += transition_cases()
    return cases


# ------------------------------------------------------------------ measuring

def decode(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")


def diff_stats(a: Image.Image, b: Image.Image) -> tuple[float, float]:
    """Mean absolute difference (percent of full scale) and the 95th percentile of the per-pixel error."""
    import numpy as np

    if a.size != b.size:
        b = b.resize(a.size, Image.LANCZOS)
    d = np.abs(np.asarray(a, dtype=np.int16) - np.asarray(b, dtype=np.int16)).astype(np.float32)
    return float(d.mean() / 2.55), float(np.percentile(d.max(axis=2), 95) / 2.55)


def side_by_side(a: Image.Image, b: Image.Image, path: Path, labels: tuple[str, str] = ("preview", "export")) -> None:
    if a.size != b.size:
        b = b.resize(a.size, Image.LANCZOS)
    d = ImageChops.difference(a, b).point(lambda v: min(255, v * 4))
    sheet = Image.new("RGB", (a.width * 3 + 8, a.height), (30, 30, 30))
    sheet.paste(a, (0, 0))
    sheet.paste(b, (a.width + 4, 0))
    sheet.paste(d, (a.width * 2 + 8, 0))
    sheet.save(path)


def grab_preview(page: Any, t: int, width: int = COMPARE_W) -> Optional[dict[str, Any]]:
    """Seek the editor to ``t`` ms, wait until every source shows the right frame, return the canvas as PNG bytes."""
    page.evaluate("([ms, w]) => { window.__lumiereGL.setWidth(w); window.__lumiereGL.seek(ms); }", [t, width])
    deadline = time.time() + 20
    while time.time() < deadline:
        page.wait_for_timeout(120)
        if page.evaluate("() => window.__lumiereGL.ready()"):
            page.wait_for_timeout(60)
            break
    snap = page.evaluate("() => window.__lumiereGL.snapshot()")
    snap["ready"] = bool(page.evaluate("() => window.__lumiereGL.ready()"))
    snap["bytes"] = base64.b64decode(snap["png"].split(",", 1)[1])
    return snap


def export_frame(srv: Server, p: Proj, t: int, work: Path, fps: float = 30.0, preset: str = "web") -> Image.Image:
    """The frame of a real export (the 'web' preset unless told otherwise) at ``t`` ms, scaled like the others."""
    key = (p.id, "export")
    path = work / f"{p.id}.mp4"
    if not path.exists():
        res = srv.post(f"/api/projects/{p.id}/render", {"preset": preset, "filename": f"{p.id}"})
        job = res.get("job") or res.get("id")
        for _ in range(600):
            renders = srv.get(f"/api/renders?project={p.id}").json()["renders"]
            done = [r for r in renders if r.get("state", "done") == "done" and r.get("path")]
            if done:
                shutil.copy(done[0]["path"], path)
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(f"export of {key} did not finish ({job})")
    png = work / f"{p.id}-{t}.png"
    n = int(round(t * fps / 1000.0))  # the frame the render shows for t (a plain -ss would take the next one)
    ff("-i", str(path), "-vf", f"select=eq(n\\,{n}),scale={COMPARE_W}:-2:flags=area", "-frames:v", "1", str(png))
    return Image.open(png).convert("RGB")


@dataclass
class Row:
    case: str
    t: int
    vs_frame: Optional[float] = None
    vs_export: Optional[float] = None
    p95: Optional[float] = None
    note: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def run(args: argparse.Namespace) -> int:
    from playwright.sync_api import sync_playwright

    work = Path(args.out or tempfile.mkdtemp(prefix="preview_check_"))
    work.mkdir(parents=True, exist_ok=True)
    data = work / "data"
    files_dir = work / "media"
    for d in (data, files_dir):
        d.mkdir(exist_ok=True)
    files = make_media(files_dir)
    srv = Server(data, free_port())
    rows: list[Row] = []
    ui_results: list[tuple[str, bool, str]] = []
    try:
        M = import_media(srv, data, files)
        cases = [] if args.ui_only else all_cases()
        if args.only:
            prefixes = tuple(args.only.split(","))
            cases = [c for c in cases if c.name.startswith(prefixes)]
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=CHROMIUM_ARGS)
            ctx = browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
            logs: list[str] = []
            for case in cases:
                page = ctx.new_page()
                page.on("console", lambda m: logs.append(m.text) if m.type in ("error", "warning") else None)
                page.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))
                try:
                    proj = case.build(srv, M, files_dir)
                except Exception as error:  # noqa: BLE001
                    rows.append(Row(case.name, 0, note=f"build failed: {error}"))
                    page.close()
                    continue
                page.goto(f"{srv.base}/#/p/{proj.id}")
                try:
                    page.wait_for_function("() => !!window.__lumiereGL", timeout=15000)
                except Exception:  # noqa: BLE001
                    page.screenshot(path=str(work / f"{case.name}-nogl.png"))
                    rows.append(Row(case.name, 0, note="preview hook never appeared"))
                    page.close()
                    continue
                proj_fps = float(proj.doc()["canvas"]["fps"])
                for t in case.times:
                    row = Row(case.name, t)
                    try:
                        snap = grab_preview(page, t, case.gl_width or COMPARE_W)
                        gl = decode(snap["bytes"])
                        if gl.width != COMPARE_W:
                            gl = gl.resize((COMPARE_W, int(round(gl.height * COMPARE_W / gl.width))), Image.BOX)
                        if case.frame:
                            frame = decode(srv.get(f"/api/projects/{proj.id}/frame", params={"t": t, "width": COMPARE_W}).content)
                            row.vs_frame, row.p95 = diff_stats(gl, frame)
                            side_by_side(gl, frame, work / f"{case.name}-{t}-frame.png", ("preview", "frame"))
                        if not snap["ready"]:
                            row.note = "sources not ready"
                        if case.export:
                            ex = export_frame(srv, proj, t, work, proj_fps, case.preset)
                            row.vs_export, p95 = diff_stats(gl, ex)
                            row.p95 = p95 if row.p95 is None else row.p95
                            side_by_side(gl, ex, work / f"{case.name}-{t}-export.png")
                    except Exception as error:  # noqa: BLE001
                        row.note = f"failed: {error}"[:200]
                    rows.append(row)
                page.close()
            browser.close()
        if args.ui or args.ui_only:
            with sync_playwright() as pw:
                ui_results = ui_checks(srv, M, work, pw)
        if logs and args.verbose:
            print("\nbrowser messages:\n  " + "\n  ".join(sorted(set(logs))[:40]))
    finally:
        srv.stop()
    print_table(rows)
    if ui_results:
        print("\neditor checks")
        for name, ok, detail in ui_results:
            print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  [{detail}]" if detail else ""))
    summary = {"work": str(work), "rows": [r.__dict__ for r in rows]}
    (work / "results.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"\nimages and results.json in {work}")
    if not args.keep and not args.out:
        for d in (data,):
            shutil.rmtree(d, ignore_errors=True)
    # the export is the reference when there is one (the single-frame route differs from it for fades and transitions)
    worst = max([r.vs_export if r.vs_export is not None else (r.vs_frame or 0) for r in rows] or [0])
    return 0 if worst < args.limit and all(ok for _, ok, _ in ui_results) else 1


# ------------------------------------------------------------------ editor behaviour (--ui)

def ui_checks(srv: Server, M: dict[str, str], work: Path, pw: Any) -> list[tuple[str, bool, str]]:
    """What the person sees and does: the toggle, the settings entry, the fallback without WebGL2 and playback on a long timeline."""
    out: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        out.append((name, bool(ok), detail))

    proj = Proj(srv, M, "ui")
    proj.add("a.mp4", src_in=0, src_out=3000)
    second = proj.add("b.mp4", src_in=1000, src_out=4000)
    proj.edit({"op": "transition", "clip": second, "type": "wipe_left", "dur": 800})
    proj.edit({"op": "add_text", "text": "Hola Lumiere", "start": 500, "length": 2000})
    url = f"{srv.base}/#/p/{proj.id}"

    gl_args = CHROMIUM_ARGS
    browser = pw.chromium.launch(args=gl_args)
    ctx = browser.new_context(viewport={"width": 1360, "height": 820})
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(url)
    page.wait_for_selector("[data-testid=gl-toggle]", timeout=20000)
    page.wait_for_function("() => !!window.__lumiereGL", timeout=20000)
    page.evaluate("() => window.__lumiereGL.seek(2500)")
    page.wait_for_timeout(1500)
    check("gl canvas is the default preview", page.locator("canvas[data-gl-preview]").count() == 1)
    check("the title overlay stays a DOM layer above the canvas", page.get_by_text("Hola Lumiere").count() >= 1)
    check("a transition frame is drawn (canvas is not blank)", _canvas_has_content(page))
    page.screenshot(path=str(work / "ui_editor_gl.png"))
    page.evaluate("() => window.__lumiereGL.seek(1200)")
    page.wait_for_timeout(1200)
    page.locator(".stage-box").screenshot(path=str(work / "ui_title_overlay.png"))

    page.click("[data-testid=gl-toggle]")
    page.wait_for_timeout(800)
    check("toggle off falls back to the CSS preview", page.locator("canvas[data-gl-preview]").count() == 0 and page.locator("video").count() >= 1)
    page.screenshot(path=str(work / "ui_editor_css.png"))
    page.click("[data-testid=gl-toggle]")
    page.wait_for_timeout(800)
    check("toggle on brings the canvas back", page.locator("canvas[data-gl-preview]").count() == 1)

    page.goto(f"{srv.base}/#/settings")
    page.get_by_text("Vista previa acelerada (WebGL)").first.wait_for(timeout=10000)
    page.screenshot(path=str(work / "ui_settings.png"))
    page.get_by_text("Vista previa acelerada (WebGL)").first.click()
    page.wait_for_timeout(300)
    stored = page.evaluate("() => localStorage.getItem('lumiere.preview.gl')")
    check("the settings switch is kept in this browser", stored == "off", f"stored={stored!r}")
    page.goto(url)
    page.wait_for_selector("[data-testid=gl-toggle]", timeout=20000)
    page.wait_for_timeout(800)
    check("a preview turned off in settings stays off in the editor", page.locator("canvas[data-gl-preview]").count() == 0)
    page.evaluate("() => localStorage.removeItem('lumiere.preview.gl')")
    page.close()
    check("no page errors", not [e for e in errors if "GPU stall" not in e and "favicon" not in e], "; ".join(errors[:3]))

    # a browser without WebGL2: the editor must still work, with the simple preview
    nogl = pw.chromium.launch(args=["--disable-3d-apis", "--disable-gpu"])
    p2 = nogl.new_context(viewport={"width": 1360, "height": 820}).new_page()
    errs2: list[str] = []
    p2.on("pageerror", lambda e: errs2.append(str(e)))
    p2.goto(url)
    p2.wait_for_selector("[data-testid=gl-toggle]", timeout=20000)
    p2.wait_for_timeout(1500)
    check("without WebGL2 the editor uses the CSS preview", p2.locator("canvas[data-gl-preview]").count() == 0 and p2.locator("video").count() >= 1)
    check("without WebGL2 the toggle is disabled", p2.locator("[data-testid=gl-toggle]").is_disabled())
    check("without WebGL2 nothing throws", not errs2, "; ".join(errs2[:2]))
    p2.screenshot(path=str(work / "ui_editor_nogl.png"))
    nogl.close()

    # playback on a long timeline: few media elements, steady drawing
    big = Proj(srv, M, "ui_long")
    for i in range(36):
        c = big.add("a.mp4" if i % 2 == 0 else "b.mp4", src_in=(i % 5) * 1000, src_out=(i % 5) * 1000 + 2500)
        if i:
            big.edit({"op": "transition", "clip": c, "type": "crossfade", "dur": 400})
    page = ctx.new_page()
    page.goto(f"{srv.base}/#/p/{big.id}")
    page.wait_for_function("() => !!window.__lumiereGL", timeout=20000)
    page.evaluate("() => window.__lumiereGL.seek(30000)")
    page.wait_for_timeout(1500)
    steady = page.evaluate("() => window.__lumiereGL.bench(8)")
    page.evaluate("() => window.__lumiereGL.seek(27600)")  # inside a crossfade
    page.wait_for_timeout(1500)
    mixing = page.evaluate("() => window.__lumiereGL.bench(8)")
    info = page.evaluate("() => window.__lumiereGL.info()")
    check("one frame costs little even on a software renderer", steady["drawn"] > 0 and steady["ms"] < 250,
          f"{info['W']}x{info['H']}: {steady['ms']:.0f} ms steady ({steady['drawn']} layers), {mixing['ms']:.0f} ms inside a crossfade ({mixing['drawn']} layers, "
          f"{mixing['missing']} missing); software rasteriser, a GPU is far faster")
    page.evaluate("() => window.__lumiereGL.seek(30000)")
    page.wait_for_timeout(800)
    before = page.evaluate("() => window.__lumiereGL.stats()")
    page.click("button[title*='Space']")
    seen = []
    for _ in range(6):
        page.wait_for_timeout(500)
        seen.append(page.evaluate("() => window.__lumiereGL.stats().videos"))
    after = page.evaluate("() => window.__lumiereGL.stats()")
    advanced = page.evaluate("() => window.__lumiereGL.info().t")
    page.click("button[title*='Space']")
    draws = after["draws"] - before["draws"]
    ms = (after["ms"] - before["ms"]) / max(1, draws)
    check("a 36-clip timeline keeps few media elements mounted", max(seen) <= 6, f"video elements while playing: {seen}")
    check("the playhead advances while playing", advanced > 30500, f"t={advanced:.0f} ms")
    check("frames keep being drawn while playing", draws >= 6, f"{draws} draws in 3 s ({draws / 3:.1f}/s), {ms:.1f} ms of CPU each (software renderer)")
    page.screenshot(path=str(work / "ui_long_timeline.png"))

    # the same playback with the simple preview, as a yardstick for how busy this machine is
    page.evaluate("() => { window.__raf = 0; const tick = () => { window.__raf += 1; requestAnimationFrame(tick); }; requestAnimationFrame(tick); }")
    page.evaluate("() => { window.__raf = 0; }")
    page.click("button[title*='Space']")
    page.wait_for_timeout(3000)
    raf_gl = page.evaluate("() => window.__raf") / 3
    page.click("button[title*='Space']")
    page.click("[data-testid=gl-toggle]")
    page.evaluate("() => window.__lumiereGL === undefined")
    page.wait_for_timeout(800)
    page.evaluate("() => { window.__raf = 0; }")
    page.click("button[title*='Space']")
    page.wait_for_timeout(3000)
    raf_css = page.evaluate("() => window.__raf") / 3
    page.click("button[title*='Space']")
    check("playing with WebGL is not slower than the simple preview", raf_gl >= 0.7 * raf_css, f"animation frames per second: {raf_gl:.1f} with WebGL, {raf_css:.1f} with the simple preview")
    page.close()
    browser.close()
    return out


def _canvas_has_content(page: Any) -> bool:
    snap = page.evaluate("() => window.__lumiereGL.snapshot()")
    img = decode(base64.b64decode(snap["png"].split(",", 1)[1]))
    colors = img.resize((64, 36)).getcolors(64 * 36)
    return bool(colors) and len(colors) > 8


def print_table(rows: list[Row]) -> None:
    print(f"\n{'case':26} {'t ms':>6} {'vs frame %':>11} {'vs export %':>12} {'p95 %':>7}  note")
    for r in rows:
        f = "-" if r.vs_frame is None else f"{r.vs_frame:.2f}"
        e = "-" if r.vs_export is None else f"{r.vs_export:.2f}"
        p = "-" if r.p95 is None else f"{r.p95:.1f}"
        print(f"{r.case:26} {r.t:6d} {f:>11} {e:>12} {p:>7}  {r.note}")
    vals = [r.vs_frame for r in rows if r.vs_frame is not None]
    if vals:
        print(f"\nmean over {len(vals)} comparisons: {sum(vals) / len(vals):.2f}%   worst: {max(vals):.2f}%")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="comma separated case-name prefixes")
    ap.add_argument("--out", default="", help="folder for images and results (default: a temp folder)")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--limit", type=float, default=4.0, help="exit code 1 when a case is above this mean difference (percent)")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--ui", action="store_true", help="also check the editor itself: toggle, settings, fallback without WebGL2, long-timeline playback")
    ap.add_argument("--ui-only", action="store_true", help="only those editor checks")
    sys.exit(run(ap.parse_args()))


if __name__ == "__main__":
    main()
