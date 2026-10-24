from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_file_encoding="utf-8-sig", extra="ignore"
    )

    app_origin: str = "http://localhost:5173"
    storage_dir: Path = ROOT / "storage"
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    segment_seconds: int = 4
    max_upload_mb: int = 2048
    db_host: str = "localhost,1433"
    db_name: str = "bvg_streaming"
    db_user: str = "sa"
    db_driver: str = "ODBC Driver 18 for SQL Server"
    db_password: str = ""
    cookie_secure: bool = False
    session_days: int = 7
    worker_poll_seconds: int = 3
    job_lease_seconds: int = 120
    job_max_attempts: int = 3
    video_bitrates: str = "480:900000,720:2200000,1080:4500000"
    audio_bitrate: int = 128000

    @property
    def storage(self) -> Path:
        return (ROOT / self.storage_dir).resolve()


settings = Settings()
