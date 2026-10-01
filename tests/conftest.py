from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pytest

ROOT = Path(__file__).resolve().parent.parent
for entry in (str(ROOT), str(ROOT / "tests")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

warnings.filterwarnings("ignore", category=DeprecationWarning)

from lumiere_hoard.config import Config  # noqa: E402
from lumiere_hoard.main import create_app  # noqa: E402
from lumiere_hoard.services import Services  # noqa: E402

# Words that must never appear in the product, its manifest or its docs (built from fragments so this file does not contain them).
BANNED_WORDS = ("chat" + "gpt", "open" + "ai", "anthro" + "pic", "lm " + "studio", "odys" + "seus", "gem" + "ini", "co" + "pilot",
                "clau" + "de", "cap" + "cut", "open" + "cut", "pre" + "miere", "da" + "vinci", "fi" + "nal cut",
                "kden" + "live", "lossless" + "cut", "auto-" + "editor", "vid" + "eo.js")

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg is not installed")


def _ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="session")
def media_dir(tmp_path_factory) -> Path:
    """Synthetic media made once per test session: speech-like tone with pauses, a vertical clip, a picture, a click track
    at 120 bpm and a video with three colour scenes."""
    d = tmp_path_factory.mktemp("media")
    if not HAS_FFMPEG:
        return d
    # 12 s, 1280x720, 30 fps; tone with silences at 3-5 s and 8-9 s
    _ff("-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=12", "-f", "lavfi", "-i", "sine=f=440:r=48000:d=12",
        "-af", "volume=enable='between(t,3,5)+between(t,8,9)':volume=0", "-c:v", "libx264", "-preset", "ultrafast", "-g", "30",
        "-c:a", "aac", "-shortest", str(d / "talk.mp4"))
    _ff("-f", "lavfi", "-i", "testsrc=s=720x1280:r=25:d=6", "-f", "lavfi", "-i", "sine=f=660:r=48000:d=6", "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", "-shortest", str(d / "vert.mp4"))
    _ff("-f", "lavfi", "-i", "color=c=0x3366cc:s=800x600", "-frames:v", "1", str(d / "pic.png"))
    # clicks every 0.5 s (120 bpm) for 12 s
    _ff("-f", "lavfi", "-i", "aevalsrc='if(lt(mod(t,0.5),0.02),sin(2*PI*1000*t)*0.9,0)':s=48000:d=12", "-c:a", "pcm_s16le", str(d / "clicks.wav"))
    # three scenes of 2 s each with very different colours
    _ff("-f", "lavfi", "-i", "color=c=red:s=640x360:r=25:d=2", "-f", "lavfi", "-i", "color=c=green:s=640x360:r=25:d=2",
        "-f", "lavfi", "-i", "color=c=blue:s=640x360:r=25:d=2", "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0", "-c:v", "libx264",
        "-preset", "ultrafast", str(d / "scenes.mp4"))
    return d


@dataclass
class FakeChatResult:
    text: str = "{}"
    model: str = "fake-model"


class FakeLink:
    def __init__(self, responder: Any = None, available: bool = True):
        self.responder = responder
        self.available = available
        self.calls: list[list[dict[str, str]]] = []
        self._lock = threading.Lock()

    def chat(self, messages, images=None, **kwargs):
        with self._lock:
            self.calls.append(messages)
        if not self.available or self.responder is None:
            raise RuntimeError("no model configured")
        text = self.responder(messages) if callable(self.responder) else self.responder
        return FakeChatResult(text=text)

    def status(self):
        return {"llm": {"state": "resolved" if self.available else "unavailable", "provider": "fake"}}

    def close(self):
        pass


class Recorder:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def __call__(self, type_, data):
        self.events.append((type_, data))

    def types(self):
        return [t for t, _ in self.events]


def make_config(tmp_path: Path, **overrides) -> Config:
    base = dict(data_dir=tmp_path / "data", port=0, data_dir_configured=True, encoder="x264", render_workers=2)
    base.update(overrides)
    return Config(**base)


def fake_transcriber(path, **kw):
    """No model in tests: an empty transcript (tests put the words they need with fake_transcript)."""
    return {"language": kw.get("language") or "es", "language_p": 1.0, "model": "fake", "device": "cpu", "words": [], "segments": []}


def make_services(tmp_path: Path, *, link: Any = None, inline: bool = True, **config_overrides) -> Services:
    svc = Services(make_config(tmp_path, **config_overrides), link=link if link is not None else FakeLink(available=False), emit_fn=Recorder(),
                   inline_jobs=inline)
    svc.transcriber = fake_transcriber
    return svc


@pytest.fixture
def services(tmp_path):
    svc = make_services(tmp_path)
    svc.start()
    yield svc
    svc.stop()


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    svc = make_services(tmp_path)
    app = create_app(svc.config, svc)
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        test_client.svc = svc
        yield test_client


def fake_transcript(svc: Services, media_id: str, words: list[tuple[int, int, str]], language: str = "es") -> None:
    from lumiere_hoard import media as media_store

    media_store.put_analysis(svc, media_id, "transcript", {"language": language, "model": "fake", "device": "cpu",
                                                          "words": [{"id": f"w{i + 1}", "t0": a, "t1": b, "text": t, "p": 0.9}
                                                                    for i, (a, b, t) in enumerate(words)],
                                                          "segments": []})


def media_lookup_from(items: dict[str, dict]) -> Any:
    return lambda mid: items.get(mid)


VIDEO = {"id": "m1", "name": "a", "kind": "video", "duration_ms": 12000, "width": 1280, "height": 720, "fps": 30, "has_audio": True, "has_video": True}
VERT = {"id": "m2", "name": "b", "kind": "video", "duration_ms": 6000, "width": 720, "height": 1280, "fps": 25, "has_audio": True, "has_video": True}
PIC = {"id": "m3", "name": "c", "kind": "image", "duration_ms": 0, "width": 800, "height": 600, "fps": 0, "has_audio": False, "has_video": True}
SONG = {"id": "m4", "name": "song", "kind": "audio", "duration_ms": 60000, "width": 0, "height": 0, "fps": 0, "has_audio": True, "has_video": False}
LOOK = media_lookup_from({"m1": VIDEO, "m2": VERT, "m3": PIC, "m4": SONG})


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], capture_output=True, text=True)
    return json.loads(out.stdout)


def nb_frames(path: Path) -> Optional[int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True)
    try:
        return int(out.stdout.strip().split(",")[0])
    except ValueError:
        return None
