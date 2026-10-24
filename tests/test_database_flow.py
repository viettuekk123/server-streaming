"""BVG_RUN_DB_TESTS=1 để kiểm tra trên SQL Server thật đã khởi tạo schema."""

import os
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.config import settings
from app.database import SessionLocal, now
from app.main import app
from app.models import LoginSession, ProcessingJob, User, Video, WatchProgress
from app.worker import claim, process

pytestmark = pytest.mark.skipif(
    os.environ.get("BVG_RUN_DB_TESTS") != "1", reason="Cần SQL Server thật"
)


def test_auth_upload_worker_progress_and_recovery():
    name = "test_" + uuid.uuid4().hex[:12]
    client = TestClient(app, headers={"Origin": settings.app_origin})
    credentials = {
        "username": name,
        "password": "StudentDemo123!",
        "confirm_password": "StudentDemo123!",
    }
    assert (
        client.post(
            "/api/videos", data={"title": "Guest"}, files={"file": ("bad", b"x")}
        ).status_code
        == 401
    )
    result = client.post("/api/auth/register", json=credentials)
    assert result.status_code == 201, result.text
    user_id = result.json()["user"]["id"]
    video_id = None
    try:
        client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        assert client.post("/api/auth/register", json=credentials).status_code == 409
        assert client.get("/api/auth/me").json()["user"]["username"] == name
        assert (
            client.post(
                "/api/videos", data={"title": "Bad"}, files={"file": ("bad.mp4", b"not a video")}
            ).status_code
            == 400
        )
        source = settings.storage / "demo-source.mp4"
        if not source.exists():
            pytest.skip("Chạy scripts.prepare_demo trước integration test")
        with source.open("rb") as file:
            result = client.post(
                "/api/videos",
                data={"title": "Video kiểm thử", "description": "Test SQL Server thật"},
                files={"file": ("test.mp4", file, "video/mp4")},
            )
        assert result.status_code == 202, result.text
        video_id = result.json()["id"]
        assert client.get(f"/api/videos/{video_id}").status_code == 404
        job = claim()
        assert job and job[1] == video_id
        # Giả lập worker chết: lease hết hạn, worker khác lấy lại và đổi ownership token.
        with SessionLocal.begin() as db:
            row = db.get(ProcessingJob, job[0])
            row.lease_until = now() - timedelta(seconds=1)
        recovered = claim()
        assert recovered and recovered[0] == job[0] and recovered[2] != job[2]
        process(*recovered)
        result = client.get(f"/api/videos/{video_id}")
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "ready"
        token = client.post(f"/api/videos/{video_id}/progress/session").json()["write_session"]
        url = f"/api/videos/{video_id}/progress"

        def save(sequence, position, write_session=token):
            return client.put(
                url,
                json={
                    "sequence": sequence,
                    "position_seconds": position,
                    "write_session": write_session,
                },
            )

        duration = result.json()["duration"]
        assert save(2, duration * 0.5).status_code == 200
        assert save(1, duration * 0.7).status_code == 409
        assert save(3, duration * 0.2).status_code == 200
        assert client.get(url).json()["position_seconds"] == pytest.approx(duration * 0.2)
        new_token = client.post(f"/api/videos/{video_id}/progress/session").json()["write_session"]
        assert save(4, duration * 0.5).status_code == 409
        assert save(1, duration * 0.3, new_token).status_code == 200
        client.headers["X-CSRF-Token"] = "invalid"
        assert client.post("/api/auth/logout").status_code == 403
    finally:
        with SessionLocal.begin() as db:
            if video_id:
                db.execute(delete(WatchProgress).where(WatchProgress.video_id == video_id))
                db.execute(delete(ProcessingJob).where(ProcessingJob.video_id == video_id))
                db.execute(delete(Video).where(Video.id == video_id))
            db.execute(delete(LoginSession).where(LoginSession.user_id == user_id))
            db.execute(delete(User).where(User.id == user_id))
