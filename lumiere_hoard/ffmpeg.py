"""Everything that touches the ffmpeg / ffprobe binaries: discovery, probing, running with progress and cancellation,
encoder detection, path escaping for filter arguments, PCM and frame extraction."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from .errors import FfmpegFailed, FfmpegMissing, LumiereError

log = logging.getLogger("lumiere.ffmpeg")

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0
WINGET_LINKS = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" if sys.platform.startswith("win") else None


class Cancelled(LumiereError):
    code = "canceled"


@dataclass
class Tools:
    ffmpeg: str
    ffprobe: str
    version: str = ""
    filters: frozenset[str] = frozenset()
    encoders: frozenset[str] = frozenset()
    nvenc_ok: Optional[bool] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def has_filter(self, name: str) -> bool:
        return name in self.filters

    def video_encoder(self, preference: str = "auto", codec: str = "h264") -> str:
        """h264_nvenc / hevc_nvenc when the GPU encoder really works (tested once), else libx264 / libx265."""
        nv = {"h264": "h264_nvenc", "hevc": "hevc_nvenc", "av1": "av1_nvenc"}[codec]
        sw = {"h264": "libx264", "hevc": "libx265", "av1": "libsvtav1"}[codec]
        if preference == "x264":
            return sw
        if nv in self.encoders and self.nvenc_works():
            return nv
        if preference == "nvenc":
            raise LumiereError("The NVIDIA encoder was requested (LUMIERE_ENCODER=nvenc) but it does not work here.", code="nvenc_unavailable")
        return sw

    def nvenc_works(self) -> bool:
        with self._lock:
            if self.nvenc_ok is None:
                self.nvenc_ok = _probe_nvenc(self.ffmpeg) if "h264_nvenc" in self.encoders else False
            return self.nvenc_ok


def _probe_nvenc(ffmpeg: str) -> bool:
    try:
        proc = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.2",
                               "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True, timeout=30, creationflags=NO_WINDOW)
        return proc.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def _which(name: str, explicit: str = "") -> str:
    if explicit:
        if Path(explicit).is_file() or shutil.which(explicit):
            return explicit
        raise FfmpegMissing(f"{name} not found at {explicit}.")
    found = shutil.which(name)
    if found:
        return found
    if WINGET_LINKS and (WINGET_LINKS / f"{name}.exe").exists():
        return str(WINGET_LINKS / f"{name}.exe")
    raise FfmpegMissing(f"{name} is not installed or not on PATH. Install ffmpeg (winget install Gyan.FFmpeg) or set LUMIERE_FFMPEG.")


def discover(ffmpeg: str = "", ffprobe: str = "") -> Tools:
    ff = _which("ffmpeg", ffmpeg)
    fp = _which("ffprobe", ffprobe)
    version = ""
    filters: set[str] = set()
    encoders: set[str] = set()
    try:
        out = subprocess.run([ff, "-hide_banner", "-version"], capture_output=True, text=True, timeout=20, creationflags=NO_WINDOW).stdout
        version = (out.splitlines() or [""])[0].replace("ffmpeg version ", "").split(" Copyright")[0]
        out = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=20, creationflags=NO_WINDOW).stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 3 and re.fullmatch(r"[TSC.]{2,3}", parts[0]) and "->" in line:
                filters.add(parts[1])
        out = subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=20, creationflags=NO_WINDOW).stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2 and re.fullmatch(r"[VAS][F.][S.][X.][B.][D.]", parts[0]):
                encoders.add(parts[1])
    except Exception as error:  # noqa: BLE001
        log.warning("Could not list ffmpeg capabilities: %s", error)
    return Tools(ff, fp, version, frozenset(filters), frozenset(encoders))


# ---------------------------------------------------------------- probing

def probe(tools: Tools, path: Path) -> dict[str, Any]:
    try:
        proc = subprocess.run([tools.ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                              capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired as error:
        raise FfmpegFailed(f"ffprobe took too long on {path.name}.") from error
    if proc.returncode != 0:
        raise FfmpegFailed(f"Not a media file ffprobe can read: {path.name} ({_tail(proc.stderr, 300)})")
    return json.loads(proc.stdout or "{}")


def _fps(stream: dict) -> float:
    for key in ("avg_frame_rate", "r_frame_rate"):
        raw = stream.get(key) or "0/0"
        try:
            num, den = raw.split("/")
            if int(den) and int(num):
                value = int(num) / int(den)
                if 0 < value < 1000:
                    return round(value, 3)
        except (ValueError, ZeroDivisionError):
            continue
    return 0.0


IMAGE_CODECS = {"png", "mjpeg", "webp", "bmp", "tiff", "gif", "jpeg2000", "jpegls"}


def summarize(info: dict[str, Any], path: Path) -> dict[str, Any]:
    """The fields the app stores for a media file."""
    streams = info.get("streams") or []
    fmt = info.get("format") or {}
    video = next((s for s in streams if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = 0.0
    for raw in (fmt.get("duration"), (video or {}).get("duration"), (audio or {}).get("duration")):
        try:
            duration = max(duration, float(raw))
        except (TypeError, ValueError):
            continue
    is_image = bool(video) and not audio and (video.get("codec_name") in IMAGE_CODECS) and duration < 0.5 or (
        bool(video) and video.get("codec_name") in IMAGE_CODECS and int(video.get("nb_frames") or 1) <= 1 and not audio)
    width, height = int((video or {}).get("width") or 0), int((video or {}).get("height") or 0)
    rotation = 0
    for side in (video or {}).get("side_data_list") or []:
        if "rotation" in side:
            try:
                rotation = int(float(side["rotation"])) % 360
            except (TypeError, ValueError):
                pass
    tags_rot = ((video or {}).get("tags") or {}).get("rotate")
    if tags_rot:
        try:
            rotation = int(tags_rot) % 360
        except ValueError:
            pass
    if rotation in (90, 270, -90, -270):
        width, height = height, width
    kind = "image" if is_image else ("video" if video else ("audio" if audio else "unknown"))
    return {
        "kind": kind,
        "duration_ms": 0 if kind == "image" else int(round(duration * 1000)),
        "width": width, "height": height,
        "fps": _fps(video) if video and kind == "video" else 0.0,
        "has_video": bool(video), "has_audio": bool(audio),
        "video_codec": (video or {}).get("codec_name"), "audio_codec": (audio or {}).get("codec_name"),
        "pix_fmt": (video or {}).get("pix_fmt"), "color_space": (video or {}).get("color_space") or "", "sample_rate": int((audio or {}).get("sample_rate") or 0),
        "channels": int((audio or {}).get("channels") or 0), "rotation": rotation,
        "bit_rate": int(fmt.get("bit_rate") or 0), "format": fmt.get("format_name"),
        "audio_streams": sum(1 for s in streams if s.get("codec_type") == "audio"),
    }


def keyframes(tools: Tools, path: Path, limit_s: Optional[float] = None) -> list[int]:
    """Keyframe times in ms (packet flags), for cuts without re-encoding."""
    args = [tools.ffprobe, "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey", "-show_entries", "frame=pts_time,best_effort_timestamp_time",
            "-of", "csv=p=0", str(path)]
    if limit_s:
        args[1:1] = ["-read_intervals", f"%+{limit_s}"]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=600, creationflags=NO_WINDOW)
    out: list[int] = []
    for line in proc.stdout.splitlines():
        for raw in line.split(","):
            try:
                out.append(int(round(float(raw) * 1000)))
                break
            except ValueError:
                continue
    return sorted(set(out))


# ---------------------------------------------------------------- running

@dataclass
class RunHandle:
    """Lets a job cancel the ffmpeg it started."""

    proc: Optional[subprocess.Popen] = None
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except OSError:
                pass


def _tail(text: str, limit: int = 1200) -> str:
    text = (text or "").strip()
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("  ")]
    text = "\n".join(lines[-12:])
    return text[-limit:]


def run(tools: Tools, args: list[str], *, duration_ms: int = 0, progress: Optional[Callable[[float], None]] = None,
        handle: Optional[RunHandle] = None, timeout: Optional[float] = None, cwd: Optional[Path] = None) -> str:
    """Run ffmpeg with ``-progress pipe:1``; report 0..1 through ``progress``; raise FfmpegFailed with the log tail."""
    cmd = [tools.ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats", *args]
    log.debug("ffmpeg %s", " ".join(cmd[1:]))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(cwd) if cwd else None,
                            creationflags=NO_WINDOW, text=True, encoding="utf-8", errors="replace")
    if handle is not None:
        handle.proc = proc
        if handle.cancelled:
            handle.cancel()
    err_chunks: list[str] = []

    def _drain():
        assert proc.stderr is not None
        for line in proc.stderr:
            err_chunks.append(line)
            if len(err_chunks) > 400:
                del err_chunks[:200]

    t = threading.Thread(target=_drain, daemon=True)
    t.start()
    started = time.monotonic()
    assert proc.stdout is not None
    for line in proc.stdout:
        if timeout and time.monotonic() - started > timeout:
            proc.kill()
            break
        if progress and duration_ms > 0 and line.startswith("out_time_us="):
            try:
                us = int(line.split("=", 1)[1])
                progress(max(0.0, min(1.0, us / 1000 / duration_ms)))
            except ValueError:
                pass
    code = proc.wait()
    t.join(timeout=5)
    err = "".join(err_chunks)
    if handle is not None and handle.cancelled:
        raise Cancelled("Canceled.")
    if code != 0:
        raise FfmpegFailed(f"ffmpeg failed ({code}): {_tail(err)}")
    if progress:
        progress(1.0)
    return err


def capture(tools: Tools, args: list[str], *, timeout: float = 3600, handle: Optional[RunHandle] = None, binary: bool = False) -> tuple[Any, str]:
    """Run ffmpeg and return (stdout, stderr) — used for analysis filters that print to the log, and raw PCM / frames."""
    cmd = [tools.ffmpeg, "-hide_banner", "-nostdin", *args]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=NO_WINDOW)
    if handle is not None:
        handle.proc = proc
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        raise FfmpegFailed("ffmpeg analysis took too long.")
    if handle is not None and handle.cancelled:
        raise Cancelled("Canceled.")
    err_text = err.decode("utf-8", "replace")
    if proc.returncode != 0:
        raise FfmpegFailed(f"ffmpeg failed ({proc.returncode}): {_tail(err_text)}")
    return (out if binary else out.decode("utf-8", "replace")), err_text


# ---------------------------------------------------------------- escaping

def filter_path(path: Path | str) -> str:
    """A path as a filter option value (subtitles=, lut3d=, vidstabtransform input=): forward slashes, the drive colon
    and quotes escaped, wrapped in single quotes. ``C:\\a b\\x.ass`` -> ``'C\\:/a b/x.ass'``."""
    text = str(path).replace("\\", "/")
    text = text.replace(":", "\\:").replace("'", "\\'")
    return f"'{text}'"


def filter_text(text: str) -> str:
    """Escape a literal for a filtergraph option inside single quotes."""
    return text.replace("\\", "\\\\").replace("'", "'\\''").replace(":", "\\:").replace("%", "\\%")


def seconds(ms: int | float) -> str:
    return f"{max(0.0, ms) / 1000:.3f}"


def fps_fraction(fps: float) -> str:
    """30 -> '30', 29.97 -> '30000/1001'."""
    known = {23.976: "24000/1001", 29.97: "30000/1001", 59.94: "60000/1001", 47.952: "48000/1001", 119.88: "120000/1001"}
    for value, frac in known.items():
        if abs(fps - value) < 0.01:
            return frac
    f = Fraction(fps).limit_denominator(1001)
    return f"{f.numerator}/{f.denominator}" if f.denominator != 1 else str(f.numerator)


def extract_pcm(tools: Tools, path: Path, *, rate: int = 16000, start_ms: int = 0, duration_ms: int = 0, stream: int = 0,
                handle: Optional[RunHandle] = None) -> bytes:
    """Mono s16le PCM of one audio stream."""
    args = ["-loglevel", "error"]
    if start_ms:
        args += ["-ss", seconds(start_ms)]
    args += ["-i", str(path)]
    if duration_ms:
        args += ["-t", seconds(duration_ms)]
    args += ["-map", f"0:a:{stream}", "-ac", "1", "-ar", str(rate), "-f", "s16le", "-acodec", "pcm_s16le", "pipe:1"]
    out, _ = capture(tools, args, binary=True, handle=handle)
    return out


def extract_frames(tools: Tools, path: Path, *, width: int, fps: float, start_ms: int = 0, duration_ms: int = 0,
                   gray: bool = False, handle: Optional[RunHandle] = None) -> tuple[bytes, int, int]:
    """Raw frames (rgb24 or gray) scaled to ``width`` at ``fps``; returns (bytes, width, height)."""
    args = ["-loglevel", "error"]
    if start_ms:
        args += ["-ss", seconds(start_ms)]
    args += ["-i", str(path)]
    if duration_ms:
        args += ["-t", seconds(duration_ms)]
    info = summarize(probe(tools, path), path)
    w = width
    h = max(2, int(round(info["height"] * width / max(1, info["width"]) / 2)) * 2) if info["width"] else width
    args += ["-an", "-vf", f"fps={fps},scale={w}:{h}:flags=area", "-f", "rawvideo", "-pix_fmt", "gray" if gray else "rgb24", "pipe:1"]
    out, _ = capture(tools, args, binary=True, handle=handle)
    return out, w, h


def grab_frame(tools: Tools, path: Path, at_ms: int, out: Path, width: int = 0) -> Path:
    """One frame as PNG/JPEG (by extension)."""
    vf = [f"scale={width}:-2"] if width else []
    args = ["-ss", seconds(at_ms), "-i", str(path), "-frames:v", "1"]
    if vf:
        args += ["-vf", ",".join(vf)]
    if out.suffix.lower() in (".jpg", ".jpeg"):
        args += ["-q:v", "3"]
    args.append(str(out))
    out.parent.mkdir(parents=True, exist_ok=True)
    run(tools, args, timeout=60)
    return out


def media_files(paths: Iterable[Path]) -> list[Path]:
    return [p for p in paths if p.suffix.lower() in MEDIA_EXTENSIONS]


MEDIA_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mts", ".m2ts", ".ts", ".wmv", ".flv", ".mpg", ".mpeg", ".3gp",
    ".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".aiff", ".aif",
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff",
}
