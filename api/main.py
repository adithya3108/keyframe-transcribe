"""FastAPI application entry point."""

from __future__ import annotations

import os
# Ensure ffmpeg is on PATH on Windows
_ffmpeg_path = r"C:\Users\adith\ffmpeg\ffmpeg-8.1.1-essentials_build\bin"
if os.path.exists(_ffmpeg_path) and _ffmpeg_path not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _ffmpeg_path + os.pathsep + os.environ.get("PATH", "")

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api.auth import DOCS_BASE
from api.db import init_db
from api.routers import health, jobs, keys, meta


def _rate_limit_key(request: Request) -> str:
    # Rate limit by API key if present, otherwise by IP
    api_key = request.headers.get("X-API-Key", "")
    return api_key if api_key else get_remote_address(request)


limiter = Limiter(key_func=_rate_limit_key)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Keyframe Transcription API",
    description=(
        "## Agent-First Video & Audio Transcription\n\n"
        "Speaker-diarized transcription powered by Whisper, Chirp 3, and Gemini 2.5 Flash.\n\n"
        "### How to use (for agents)\n"
        "1. **Create an API key**: `POST /keys` — no auth needed\n"
        "2. **Submit a job**: `POST /jobs` (URL) or `POST /jobs/upload` (file)\n"
        "3. **Poll status**: `GET /jobs/{job_id}` every 5–10 seconds\n"
        "4. **Fetch result**: `GET /jobs/{job_id}/result` when status='completed'\n\n"
        "### Authentication\n"
        "Include your key in every request: `X-API-Key: kf_live_...`\n\n"
        "### Agent Discovery\n"
        "- Machine-readable overview: [`/llms.txt`](/llms.txt)\n"
        "- Plugin manifest: [`/.well-known/ai-plugin.json`](/.well-known/ai-plugin.json)\n"
        "- MCP server: see README for Claude Desktop config\n\n"
        "### Error responses\n"
        "All errors include `code`, `retryable`, `retry_after_seconds`, and `suggested_action`."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={"name": "Keyframe API", "email": "api@keyframe.ink"},
    license_info={"name": "Proprietary"},
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(jobs.router)
app.include_router(keys.router)
app.include_router(meta.router)


@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "Keyframe Transcription API",
        "version": "1.0.0",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "llms_txt": "/llms.txt",
        "health": "/health",
        "get_started": "POST /keys to create an API key, then POST /jobs to submit a transcription job.",
    }
