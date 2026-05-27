"""Health and status endpoints."""

from __future__ import annotations

import os
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["Health"])

VERSION = "1.0.0"


@router.get(
    "/health",
    summary="Health check",
    description="Returns 200 OK if the service is running. Use this to verify the service is alive before sending work.",
    responses={200: {"description": "Service is healthy."}},
)
async def health():
    return {"status": "ok", "version": VERSION}


@router.get(
    "/status",
    summary="Detailed service status",
    description="Returns service version and upstream GCP project configuration status. Does not make live API calls.",
    responses={200: {"description": "Detailed status information."}},
)
async def service_status():
    gcp_configured = bool(os.getenv("GCP_PROJECT_ID")) and bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
    return {
        "status": "ok",
        "version": VERSION,
        "upstreams": {
            "gemini": "configured" if gcp_configured else "not_configured",
            "chirp3": "configured" if gcp_configured else "not_configured",
            "whisper": "local",
        },
        "gcp_project": os.getenv("GCP_PROJECT_ID", "not_set"),
    }
