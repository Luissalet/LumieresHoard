from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image
from PIL import ImageChops

from lumiere_hoard.creative_engines import CreativeEngineError, CreativeEngines


def test_portable_discovery_config_and_project_path_guard(tmp_path, monkeypatch):
    photo = tmp_path / "portable" / "effectcraft-0.3.1-windows-x64-portable" / "effectcraft-cli.exe"
    photo.parent.mkdir(parents=True)
    photo.write_bytes(b"fixture")
    monkeypatch.setenv("LUMIERE_CRAFT_BUNDLES", str(photo.parent.parent))
    engines = CreativeEngines(tmp_path / "data")
    if os.name == "nt":  # the portable bundles are Windows builds; elsewhere only the explicit config counts
        assert engines.executable("effectcraft") == photo.resolve()
    config = tmp_path / "custom-filmcraft.exe"
    config.write_bytes(b"configured")
    engines.config_path.write_text(json.dumps({"filmcraft": str(config)}), encoding="utf-8")
    assert engines.executable("filmcraft") == config.resolve()
    project_id = "a" * 32
    folder = engines._project_dir(project_id)
    engines._guard_paths("effectcraft", [{"arguments": {"path": str(folder / "render.png")}}], folder)
    with pytest.raises(CreativeEngineError, match="inside this creative project folder"):
        engines._guard_paths("filmcraft", [{"arguments": {"path": str(tmp_path / "original.mp4")}}], folder)
    with pytest.raises(CreativeEngineError, match="media_import"):
        engines._guard_paths("filmcraft", [{"tool": "media_import", "arguments": {"text": str(tmp_path / "original.mp4")}}], folder)


def _configured() -> CreativeEngines:
    data = os.environ.get("LUMIERE_CREATIVE_TEST_DATA", "")
    if not data:
        pytest.skip("set LUMIERE_CREATIVE_TEST_DATA to an isolated directory for real engine tests")
    engines = CreativeEngines(Path(data))
    if not engines.executable("effectcraft") or not engines.executable("filmcraft"):
        pytest.skip("configure both portable EffectCraft and FilmCraft CLIs for real engine tests")
    return engines


@pytest.mark.skipif(not os.environ.get("LUMIERE_CREATIVE_TEST_DATA"), reason="opt-in real executable integration")
def test_effectcraft_title_card_is_editable_keyframed_and_rendered():
    engines = _configured()
    result = engines.create_title_card(text="Lumiere title", width=320, height=180, fps=24, duration=1.5)
    project = Path(result["native_path"])
    preview = Path(result["preview_path"])
    assert project.is_file() and project.stat().st_size > 100
    with Image.open(preview) as image:
        assert image.size == (320, 180)
        rgb = image.convert("RGB")
        assert len(rgb.getcolors(maxcolors=320 * 180) or []) > 2
    opacity = next(c for c in result["calls"] if c["tool"] == "get_property")
    prop = json.loads(opacity["content"][0]["text"])
    assert len(prop.get("keys", [])) == 4 and prop.get("animated") is True
    saved = engines.get(result["id"])
    assert saved["state"] == "complete" and saved["editable"]
    catalogue = engines.tools("effectcraft")
    assert catalogue["count"] == 21
    proxy = engines.call(result["id"], [{"tool": "get_project", "arguments": {}}, {"tool": "get_comp", "arguments": {}}])
    assert proxy["ok"] and [call["tool"] for call in proxy["calls"] if call["tool"] not in {"open_project", "save_project"}] == ["get_project", "get_comp"]

    rendered = engines.render_title_video(result["id"])
    mp4 = Path(rendered["render_path"])
    assert mp4.is_file() and mp4.stat().st_size > 1000
    assert rendered["render_state"] == "complete" and rendered["render_codec"] == "h264"
    assert rendered["render_fps"] == pytest.approx(24)
    assert rendered["render_duration_seconds"] == pytest.approx(1.5, abs=1 / 24)
    assert rendered["render_frame_count"] == 36
    assert rendered["media_receive_url"].endswith(f"/api/creative/{result['id']}/render")
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg is required to verify distinct frames in the opt-in real render test"
    start_frame, middle_frame = mp4.parent / "qa-start.png", mp4.parent / "qa-middle.png"
    for at, destination in ((0.05, start_frame), (0.75, middle_frame)):
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", str(at), "-i", str(mp4),
                        "-frames:v", "1", str(destination)], check=True, timeout=30)
    with Image.open(start_frame).convert("RGB") as first, Image.open(middle_frame).convert("RGB") as middle:
        difference = ImageChops.difference(first, middle)
        assert difference.getbbox() is not None, "title opacity keyframes should produce visibly different frames"


@pytest.mark.skipif(not os.environ.get("LUMIERE_CREATIVE_TEST_DATA"), reason="opt-in real executable integration")
def test_filmcraft_imports_copy_saves_project_and_exports_video(tmp_path):
    engines = _configured()
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg and ffprobe are required to generate and verify the isolated source")
    source = tmp_path / "synthetic-source.mp4"
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=0x366a9a:s=160x90:r=24:d=1.25", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", str(source)], check=True, timeout=30)
    original = hashlib.sha256(source.read_bytes()).hexdigest()
    result = engines.create_film_sequence(source, source_media_id="med_test1234", width=160, height=90, fps=24)
    project = Path(result["native_path"])
    render = Path(result["render_path"])
    assert project.is_file() and project.stat().st_size > 100
    assert render.is_file() and render.stat().st_size > 1000
    assert Path(result["source_copy"]).is_file()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original
    probe = subprocess.run([ffprobe, "-v", "error", "-show_entries", "stream=codec_type,width,height", "-of", "json", str(render)],
                           check=True, capture_output=True, text=True, timeout=30)
    streams = json.loads(probe.stdout)["streams"]
    assert any(s.get("codec_type") == "video" and s.get("width") == 160 and s.get("height") == 90 for s in streams)
    sequence = next(c for c in result["calls"] if c["tool"] == "sequence_inspect")
    timeline = json.loads(sequence["content"][0]["text"])
    assert any(track.get("items") for track in timeline.get("video", []))
    catalogue = engines.tools("filmcraft")
    assert catalogue["count"] == 17
    proxy = engines.call(result["id"], [{"tool": "project_inspect", "arguments": {}}, {"tool": "sequence_inspect", "arguments": {}}])
    assert proxy["ok"] and any(call["tool"] == "command_run:file.open" for call in proxy["calls"])


@pytest.mark.skipif(not os.environ.get("LUMIERE_CREATIVE_TEST_DATA"), reason="opt-in real executable integration")
def test_effectcraft_render_video_api_returns_downloadable_native_h264(client):
    created = client.post("/api/creative/title-card", json={"text": "API animated title", "width": 160,
                                                             "height": 90, "fps": 12, "duration": 1})
    assert created.status_code == 200, created.text
    creative_id = created.json()["id"]
    exported = client.post(f"/api/creative/{creative_id}/render-video", json={})
    assert exported.status_code == 200, exported.text
    body = exported.json()
    assert body["render_codec"] == "h264" and body["render_fps"] == pytest.approx(12)
    assert body["render_duration_seconds"] == pytest.approx(1)
    response = client.get(body["render_url"])
    assert response.status_code == 200 and response.headers["content-type"].startswith("video/mp4")
    assert response.content[:8][4:8] == b"ftyp"
