import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth import current_user, write_user
from app.database import get_db, now
from app.models import User, Video, WatchProgress
from app.schemas import ProgressUpdate

router = APIRouter(prefix="/api/videos", tags=["progress"])


def ready_video(db: Session, video_id: str) -> Video:
    video = db.get(Video, video_id)
    if not video or video.status != "ready":
        raise HTTPException(404, "Không tìm thấy video")
    return video


@router.get("/{video_id}/progress")
def get_progress(video_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ready_video(db, video_id)
    row = db.scalar(select(WatchProgress).where(WatchProgress.user_id == user.id, WatchProgress.video_id == video_id))
    return {"position_seconds": row.position_seconds if row else 0, "completed": row.completed if row else False}


@router.post("/{video_id}/progress/session")
def start_progress_session(video_id: str, user: User = Depends(write_user), db: Session = Depends(get_db)):
    ready_video(db, video_id)
    # Khóa user row để hai tab tạo bản ghi progress đầu tiên không đụng unique constraint.
    db.scalar(select(User).where(User.id == user.id).with_hint(User, "WITH (UPDLOCK, ROWLOCK)", "mssql"))
    row = db.scalar(select(WatchProgress).where(WatchProgress.user_id == user.id, WatchProgress.video_id == video_id))
    token = uuid.uuid4().hex
    if row:
        row.write_session = token
        row.sequence = 0
    else:
        row = WatchProgress(id=uuid.uuid4().hex, user_id=user.id, video_id=video_id, write_session=token)
        db.add(row)
    db.commit()
    return {"write_session": token, "position_seconds": 0 if row.completed else row.position_seconds, "completed": row.completed}


@router.put("/{video_id}/progress")
def save_progress(video_id: str, body: ProgressUpdate, user: User = Depends(write_user), db: Session = Depends(get_db)):
    video = ready_video(db, video_id)
    if body.position_seconds > video.duration + 0.5:
        raise HTTPException(400, "Vị trí vượt thời lượng video")
    position = min(body.position_seconds, video.duration)
    result = db.execute(update(WatchProgress).where(WatchProgress.user_id == user.id, WatchProgress.video_id == video_id,
                        WatchProgress.write_session == body.write_session, WatchProgress.sequence < body.sequence)
                        .values(position_seconds=position, completed=position >= video.duration * 0.95, sequence=body.sequence, updated_at=now()))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Cập nhật cũ hoặc phiên xem đã được thay thế bởi tab khác")
    db.commit()
    return {"ok": True}
