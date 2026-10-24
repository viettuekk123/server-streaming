import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import router as auth_router
from app.config import settings
from app.media_api import router as media_router
from app.progress import router as progress_router
from app.videos import router as videos_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = FastAPI(title="BVG Streaming", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.app_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)

app.include_router(media_router)
app.include_router(auth_router)
app.include_router(videos_router)
app.include_router(progress_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
