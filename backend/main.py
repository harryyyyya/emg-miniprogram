"""
FastAPI application entrypoint.

Run with:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""
import os
from pathlib import Path


def _load_local_env() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_local_env()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from models import init_db
from routers import ai, auth, devices, forum, health, upload, web

init_db()

app = FastAPI(
    title="EMG Prosthetic Backend API",
    description="Backend API for auth, devices, EMG upload, health reports, AI chat, and forum features.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path("uploads/images")
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/images", StaticFiles(directory=str(static_dir)), name="static_images")

app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(upload.router)
app.include_router(health.router)
app.include_router(ai.router)
app.include_router(forum.router)
app.include_router(web.router)


@app.get("/", tags=["health"])
def root():
    return {"status": "ok", "message": "EMG prosthetic backend is running."}


@app.get("/ping", tags=["health"])
def ping():
    return {"pong": True}
