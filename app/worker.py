"""Một worker xử lý tuần tự một job. Có thể chạy nhiều tiến trình, claim không trùng."""

import logging
import threading
import time
import uuid
from datetime import timedelta

from sqlalchemy import select, text, update

from app.config import settings
from app.database import SessionLocal, now
from app.media import build_media
from app.models import ProcessingJob, Video

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def claim() -> tuple[str, str, str] | None:
    token = uuid.uuid4().hex
    with SessionLocal.begin() as db:
        # UPDLOCK giữ quyền claim đến cuối transaction, READPAST bỏ qua job worker khác đang khóa.
        job = (
            db.execute(
                text("""
            SELECT TOP (1) id, video_id, attempts
            FROM processing_jobs WITH (UPDLOCK, READPAST, ROWLOCK)
            WHERE status = 'queued' OR (status = 'processing' AND lease_until < :now)
            ORDER BY updated_at, id
        """),
                {"now": now()},
            )
            .mappings()
            .first()
        )
        if not job:
            return None
        if job["attempts"] >= settings.job_max_attempts:
            db.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == job["id"])
                .values(status="failed", error="Đã hết số lần xử lý", updated_at=now())
            )
            db.execute(
                update(Video)
                .where(Video.id == job["video_id"])
                .values(
                    status="failed",
                    error="Xử lý bị gián đoạn nhiều lần. Vui lòng upload lại.",
                )
            )
            return None
        db.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == job["id"])
            .values(
                status="processing",
                attempts=job["attempts"] + 1,
                worker_token=token,
                lease_until=now() + timedelta(seconds=settings.job_lease_seconds),
                updated_at=now(),
            )
        )
        db.execute(
            update(Video).where(Video.id == job["video_id"]).values(status="processing", error=None)
        )
        return job["id"], job["video_id"], token


def heartbeat(job_id: str, token: str, stop: threading.Event):
    while not stop.wait(max(1, settings.job_lease_seconds // 3)):
        try:
            with SessionLocal.begin() as db:
                db.execute(
                    update(ProcessingJob)
                    .where(
                        ProcessingJob.id == job_id,
                        ProcessingJob.worker_token == token,
                        ProcessingJob.status == "processing",
                    )
                    .values(
                        lease_until=now() + timedelta(seconds=settings.job_lease_seconds),
                        updated_at=now(),
                    )
                )
        except Exception:
            logger.exception("Không cập nhật được heartbeat")


def process(job_id: str, video_id: str, token: str):
    stop = threading.Event()
    thread = threading.Thread(target=heartbeat, args=(job_id, token, stop), daemon=True)
    thread.start()
    try:
        # Mỗi lần chạy có generation riêng. Worker mất lease không được công khai kết quả cũ.
        output = settings.storage / "videos" / video_id / token
        manifest = build_media(
            settings.storage / "sources" / video_id / "source", output, video_id, token
        )
        with SessionLocal.begin() as db:
            result = db.execute(
                update(ProcessingJob)
                .where(
                    ProcessingJob.id == job_id,
                    ProcessingJob.worker_token == token,
                    ProcessingJob.status == "processing",
                )
                .values(status="done", lease_until=None, updated_at=now(), error=None)
            )
            if result.rowcount == 1:
                db.execute(
                    update(Video)
                    .where(Video.id == video_id)
                    .values(
                        status="ready",
                        generation=token,
                        duration=manifest["duration"],
                        error=None,
                    )
                )
        logger.info("Đã xử lý video %s", video_id)
    except Exception as error:
        logger.exception("Lỗi xử lý video %s", video_id)
        with SessionLocal.begin() as db:
            job = db.scalar(
                select(ProcessingJob)
                .where(ProcessingJob.id == job_id, ProcessingJob.worker_token == token)
                .with_hint(ProcessingJob, "WITH (UPDLOCK, ROWLOCK)", "mssql")
            )
            if job and job.status == "processing":
                failed = job.attempts >= settings.job_max_attempts
                job.status = "failed" if failed else "queued"
                job.error = str(error)[-3500:]
                job.lease_until = None
                job.updated_at = now()
                video = db.get(Video, video_id)
                video.status = "failed" if failed else "uploaded"
                video.error = (
                    "Không xử lý được video. Vui lòng kiểm tra file hoặc cấu hình FFmpeg."
                    if failed
                    else "Đang chờ thử xử lý lại."
                )
    finally:
        stop.set()
        thread.join(timeout=5)


if __name__ == "__main__":
    logger.info("Worker đang chờ job (Ctrl+C để dừng)")
    try:
        while True:
            try:
                job = claim()
                if job:
                    process(*job)
                else:
                    time.sleep(settings.worker_poll_seconds)
            except Exception:
                logger.exception("Không lấy được job")
                time.sleep(settings.worker_poll_seconds)
    except KeyboardInterrupt:
        logger.info("Worker đã dừng; job hết lease sẽ được phục hồi ở lần chạy sau.")
