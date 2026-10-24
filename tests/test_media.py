from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.media import dimensions, parse_mpd, rendition_sizes


def test_sizes_no_upscale_and_portrait():
    assert rendition_sizes(640, 360) == [(360, 640, 360)]
    assert rendition_sizes(1080, 1920) == [
        (480, 480, 852),
        (720, 720, 1280),
        (1080, 1080, 1920),
    ]
    assert dimensions({"width": 1920, "height": 1080, "side_data_list": [{"rotation": 90}]}) == (
        1080,
        1920,
    )


def test_manifest_uses_real_timeline_and_sizes(tmp_path: Path):
    (tmp_path / "init.mp4").write_bytes(b"init")
    for i in range(1, 4):
        (tmp_path / f"seg-{i:05d}.m4s").write_bytes(b"sample" * i)
    mpd = tmp_path / "index.mpd"
    mpd.write_text(
        """<MPD xmlns="urn:mpeg:dash:schema:mpd:2011"><Period><AdaptationSet mimeType="video/mp4"><Representation codecs="avc1.640029" bandwidth="900000" width="852" height="480"><SegmentTemplate timescale="1000" startNumber="1"><SegmentTimeline><S t="0" d="4100" r="1"/><S d="500"/></SegmentTimeline></SegmentTemplate></Representation></AdaptationSet></Period></MPD>"""
    )
    result = parse_mpd(mpd, "/media", "480p")
    assert [s["start"] for s in result["segments"]] == [0, 4.1, 8.2]
    assert result["segments"][-1]["duration"] == 0.5
    assert result["segments"][-1]["bytes"] == 18
    (tmp_path / "seg-00003.m4s").unlink()
    with pytest.raises(FileNotFoundError):
        parse_mpd(mpd, "/media", "480p")


def test_media_rejects_traversal_before_db():
    client = TestClient(app)
    assert client.get("/api/media/bad!id/v1/source").status_code == 404


def test_health_does_not_require_database():
    assert TestClient(app).get("/api/health").json() == {"status": "ok"}
