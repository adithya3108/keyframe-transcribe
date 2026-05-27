"""Job submission and status endpoints."""

from __future__ import annotations

import asyncio
import datetime
import os
import tempfile
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from api.auth import DOCS_BASE, require_api_key
from api.db import get_db
from api.models import ErrorDetail, ErrorResponse, JobStatusResponse, JobSubmitURL
from api.pricing import check_and_reserve_quota
from api.worker import run_pipeline

router = APIRouter(prefix="/jobs", tags=["Jobs"])

MAX_FILE_BYTES = 100 * 1024 * 1024  # 100 MB
ALLOWED_MIMES = {
    "video/mp4", "video/quicktime", "video/x-msvideo", "video/webm",
    "audio/mpeg", "audio/mp4", "audio/wav", "audio/ogg", "audio/webm",
    "audio/x-wav", "audio/flac",
}


def _job_response(row, request: Request) -> dict:
    base = str(request.base_url).rstrip("/")
    resp = {
        "job_id": row["id"],
        "status": row["status"],
        "poll_url": f"{base}/jobs/{row['id']}",
        "result_url": f"{base}/jobs/{row['id']}/result" if row["status"] == "completed" else None,
        "error": None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if row["status"] == "failed" and row["error_code"]:
        resp["error"] = {
            "code": row["error_code"],
            "message": row["error_message"] or "Unknown error.",
            "retryable": row["error_code"] in ("UPSTREAM_QUOTA_EXCEEDED", "UPSTREAM_TIMEOUT", "UPSTREAM_ERROR"),
            "retry_after_seconds": 60 if row["error_code"] == "UPSTREAM_QUOTA_EXCEEDED" else None,
            "suggested_action": _suggested_action(row["error_code"]),
            "docs_url": f"{DOCS_BASE}/docs#errors",
        }
    return resp


def _suggested_action(code: str) -> str:
    return {
        "UPSTREAM_QUOTA_EXCEEDED": "Wait 60 seconds then resubmit the job.",
        "UPSTREAM_TIMEOUT": "Resubmit the job; it may succeed on retry.",
        "UPSTREAM_ERROR": "Resubmit the job; upstream service was temporarily unavailable.",
        "PIPELINE_ERROR": "Check the file format and resubmit. If this persists contact support.",
    }.get(code, "Review the error and resubmit.")


@router.post(
    "",
    summary="Submit a video/audio URL for transcription",
    description=(
        "Submit a publicly accessible video or audio URL for async transcription. "
        "Returns a job_id immediately. Poll GET /jobs/{job_id} until status='completed', "
        "then fetch the transcript at GET /jobs/{job_id}/result. "
        "Typical processing time: 10–60 seconds per video."
    ),
    response_model=JobStatusResponse,
    status_code=202,
    responses={
        202: {"description": "Job accepted. Poll the returned poll_url for status."},
        401: {"model": ErrorResponse, "description": "Invalid or missing API key."},
        413: {"model": ErrorResponse, "description": "File too large (max 100MB)."},
        429: {"model": ErrorResponse, "description": "Rate limit or quota exceeded."},
    },
)
async def submit_url_job(
    body: JobSubmitURL,
    request: Request,
    key: dict = Depends(require_api_key),
):
    await check_and_reserve_quota(key["id"], key["tier"])
    return await _create_job(request, key, source_url=body.url, model=body.model)


@router.post(
    "/upload",
    summary="Upload a video/audio file for transcription",
    description=(
        "Upload a video or audio file (max 100MB) for async transcription. "
        "Returns a job_id immediately. Poll GET /jobs/{job_id} until status='completed', "
        "then fetch the transcript at GET /jobs/{job_id}/result."
    ),
    response_model=JobStatusResponse,
    status_code=202,
    responses={
        202: {"description": "Job accepted."},
        401: {"model": ErrorResponse},
        413: {"model": ErrorResponse, "description": "File too large (max 100MB)."},
        415: {"model": ErrorResponse, "description": "Unsupported media type."},
        429: {"model": ErrorResponse},
    },
)
async def submit_file_job(
    request: Request,
    file: UploadFile = File(..., description="Video or audio file to transcribe."),
    model: Optional[str] = Form(None, description="Optional: force a specific Gemini model."),
    key: dict = Depends(require_api_key),
):
    await check_and_reserve_quota(key["id"], key["tier"])

    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIMES and not content_type.startswith(("video/", "audio/")):
        raise HTTPException(
            status_code=415,
            detail={"error": {
                "code": "UNSUPPORTED_FORMAT",
                "message": f"Content-Type '{content_type}' is not supported.",
                "retryable": False,
                "retry_after_seconds": None,
                "suggested_action": "Upload an mp4, mov, avi, webm, mp3, wav, flac, or ogg file.",
                "docs_url": f"{DOCS_BASE}/docs#supported-formats",
            }},
        )

    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error": {
                "code": "FILE_TOO_LARGE",
                "message": "File exceeds 100MB limit.",
                "retryable": False,
                "retry_after_seconds": None,
                "suggested_action": "Compress the file or use a URL pointing to a smaller file.",
                "docs_url": f"{DOCS_BASE}/docs#file-limits",
            }},
        )

    suffix = os.path.splitext(file.filename or ".mp4")[1] or ".mp4"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(data)
    tmp.close()

    return await _create_job(request, key, file_path=tmp.name, model=model)


async def _create_job(
    request: Request,
    key: dict,
    source_url: str | None = None,
    file_path: str | None = None,
    model: str | None = None,
) -> dict:
    job_id = str(uuid.uuid4())
    now = datetime.datetime.utcnow().isoformat()

    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO jobs (id, api_key_id, status, file_path, source_url, created_at, updated_at) VALUES (?, ?, 'queued', ?, ?, ?, ?)",
            (job_id, key["id"], file_path, source_url, now, now),
        )
        await db.commit()
    finally:
        await db.close()

    asyncio.create_task(run_pipeline(job_id, file_path, source_url, key["id"], key["tier"], model))

    base = str(request.base_url).rstrip("/")
    return {
        "job_id": job_id,
        "status": "queued",
        "poll_url": f"{base}/jobs/{job_id}",
        "result_url": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }


@router.get(
    "/{job_id}",
    summary="Poll job status",
    description=(
        "Check the current status of a transcription job. "
        "Status values: 'queued' → 'processing' → 'completed' or 'failed'. "
        "Poll every 5–10 seconds. When status='completed', fetch the result at the returned result_url."
    ),
    response_model=JobStatusResponse,
    responses={
        200: {"description": "Job status. Check the 'status' field."},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse, "description": "Job not found."},
    },
)
async def get_job_status(job_id: str, request: Request, key: dict = Depends(require_api_key)):
    row = await _fetch_job(job_id, key["id"])
    return _job_response(row, request)


@router.get(
    "/{job_id}/result",
    summary="Fetch transcription result",
    description=(
        "Retrieve the full TranscriptionResult for a completed job. "
        "Returns 404 if the job doesn't exist, 400 if it isn't completed yet."
    ),
    responses={
        200: {"description": "Full TranscriptionResult with speaker-diarized transcript."},
        400: {"model": ErrorResponse, "description": "Job not yet completed."},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def get_job_result(job_id: str, key: dict = Depends(require_api_key)):
    import json as _json
    row = await _fetch_job(job_id, key["id"])

    if row["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail={"error": {
                "code": "RESULT_NOT_READY",
                "message": f"Job status is '{row['status']}', not 'completed'.",
                "retryable": row["status"] in ("queued", "processing"),
                "retry_after_seconds": 5,
                "suggested_action": "Poll GET /jobs/{job_id} until status='completed', then retry this endpoint.",
                "docs_url": f"{DOCS_BASE}/docs#polling",
            }},
        )

    return _json.loads(row["result_json"])


async def _fetch_job(job_id: str, api_key_id: str):
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT * FROM jobs WHERE id = ? AND api_key_id = ?",
            (job_id, api_key_id),
        )
    finally:
        await db.close()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail={"error": {
                "code": "JOB_NOT_FOUND",
                "message": f"Job '{job_id}' not found.",
                "retryable": False,
                "retry_after_seconds": None,
                "suggested_action": "Verify the job_id. Jobs belong to the API key that created them.",
                "docs_url": f"{DOCS_BASE}/docs#jobs",
            }},
        )
    return rows[0]
