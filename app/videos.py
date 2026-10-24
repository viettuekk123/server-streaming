import json
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import current_user, write_user
from app.config import settings
from app.database import SessionLocal, get_db
from app.media import probe
from app.models import ProcessingJob, User, Video

router = APIRouter(prefix="/api/videos", tags=["videos"])
logger = logging.getLogger(__name__)


def ready_generation(video_id: str) -> str | None:
    with SessionLocal() as db:
        return db.scalar(select(Video.generation).where(Video.id == video_id, Video.status == "ready"))


def public_video(video: Video, username: str) -> dict:
    return {"id": video.id, "title": video.title, "description": video.description, "username": username,
            "status": video.status, "error": video.error, "duration": video.duration,
            "created_at": video.created_at.isoformat() + "Z",
            "thumbnail_url": f"/api/media/{video.id}/{video.generation}/thumbnail.jpg" if video.status == "ready" else None}


@router.get("")
def list_videos(q: str = Query("", max_length=200), page: int = Query(1, ge=1), db: Session = Depends(get_db)):
    conditions = [Video.status == "ready"]
    if q.strip():
        conditions.append(Video.title.contains(q.strip(), autoescape=True))
    total = db.scalar(select(func.count()).select_from(Video).where(*conditions))
    rows = db.execute(select(Video, User.username).join(User, Video.user_id == User.id).where(*conditions)
                      .order_by(Video.created_at.desc(), Video.id).offset((page - 1) * 12).limit(12)).all()
    return {"items": [public_video(video, name) for video, name in rows], "total": total, "page": page, "page_size": 12}


@router.get("/mine")
def my_videos(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Video).where(Video.user_id == user.id).order_by(Video.created_at.desc())).all()
    return [public_video(video, user.username) for video in rows]


@router.post("", status_code=202)
def upload(title: str = Form(..., min_length=1, max_length=200), description: str = Form("", max_length=5000),
           file: UploadFile = File(...), user: User = Depends(write_user), db: Session = Depends(get_db)):
    if not title.strip():
        raise HTTPException(400, "Tiêu đề không được để trống")
    video_id = uuid.uuid4().hex
    folder = settings.storage / "sources" / video_id
    folder.mkdir(parents=True)
    source = folder / "source"
    try:
        size = 0
        with source.open("wb") as target:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(413, "File vượt giới hạn dung lượng")
                target.write(chunk)
        try:
            probe(source)
        except (RuntimeError, ValueError, KeyError) as error:
            logger.info("Upload không hợp lệ: %s", error)
            raise HTTPException(400, "Không đọc được video. Hãy chọn file video hợp lệ.")
        video = Video(id=video_id, user_id=user.id, title=title.strip(), description=description.strip(), status="uploaded")
        db.add(video)
        db.flush()
        db.add(ProcessingJob(id=uuid.uuid4().hex, video_id=video_id, status="queued"))
        db.commit()
        return public_video(video, user.username)
    except Exception:
        db.rollback()
        shutil.rmtree(folder)
        raise
    finally:
        file.file.close()


@router.get("/{video_id}/manifest")
def manifest(video_id: str, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video or video.status != "ready":
        raise HTTPException(404, "Video chưa sẵn sàng")
    path = settings.storage / "videos" / video.id / video.generation / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/{video_id}")
def detail(video_id: str, db: Session = Depends(get_db)):
    row = db.execute(select(Video, User.username).join(User, Video.user_id == User.id).where(Video.id == video_id, Video.status == "ready")).first()
    if not row:
        raise HTTPException(404, "Không tìm thấy video")
    return public_video(*row)
