import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import settings

router = APIRouter()


def safe_name(value: str) -> bool:
    return bool(value) and len(value) <= 64 and all(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in value)


def media_root(video_id: str, generation: str) -> Path:
    if not safe_name(video_id) or not safe_name(generation):
        raise HTTPException(404, "Không tìm thấy video")
    if (settings.storage / "demo" / video_id / generation / "manifest.json").is_file():
        return settings.storage / "demo" / video_id / generation
    # Chỉ generation ready được công khai; backend nghiệp vụ bổ sung hàm này.
    from app.videos import ready_generation
    if ready_generation(video_id) != generation:
        raise HTTPException(404, "Video chưa sẵn sàng")
    return settings.storage / "videos" / video_id / generation


def read_manifest(root: Path) -> dict:
    path = root / "manifest.json"
    if not path.is_file():
        raise HTTPException(404, "Không tìm thấy manifest")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/api/demo/{video_id}/manifest")
def demo_manifest(video_id: str):
    if not safe_name(video_id):
        raise HTTPException(404)
    return read_manifest(settings.storage / "demo" / video_id / "v1")


@router.get("/api/media/{video_id}/{generation}/{asset:path}")
def asset(video_id: str, generation: str, asset: str):
    root = media_root(video_id, generation)
    manifest = read_manifest(root)
    prefix = f"/api/media/{video_id}/{generation}/"
    allowed = {"thumbnail.jpg"}
    for track in [*manifest["renditions"], manifest.get("audio")]:
        if track:
            allowed.add(track["init_url"].removeprefix(prefix))
            allowed.update(s["url"].removeprefix(prefix) for s in track["segments"])
    path = (root / asset).resolve()
    if asset not in allowed or not path.is_relative_to(root.resolve()) or not path.is_file():
        raise HTTPException(404, "Không tìm thấy media")
    content_type = "image/jpeg" if asset.endswith(".jpg") else ("audio/mp4" if asset.startswith("audio/") else "video/mp4")
    # no-store giúp demo throughput không bị cache làm sai số; có thể đổi cho production.
    return FileResponse(path, media_type=content_type, headers={"Cache-Control": "no-store"})
