"""Agent-discoverability endpoints: llms.txt, .well-known, ai-plugin.json."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, JSONResponse

router = APIRouter(tags=["Agent Discoverability"])

LLMS_TXT = """\
# Keyframe Transcription API

> Speaker-diarized video/audio transcription with language detection and translation.
> Powered by Whisper (language detection), Chirp 3 (speaker diarization), and Gemini 2.5 Flash.

## Quick Start for Agents

### 1. Get an API key
```
POST /keys
Content-Type: application/json

{"name": "my-agent", "tier": "free"}
```
Response: `{"id": "...", "key": "kf_live_...", ...}` — save the key, shown once.

### 2. Submit a job (URL)
```
POST /jobs
X-API-Key: kf_live_...
Content-Type: application/json

{"url": "https://example.com/video.mp4"}
```
Response: `{"job_id": "...", "status": "queued", "poll_url": "/jobs/..."}`

### 3. Submit a job (file upload)
```
POST /jobs/upload
X-API-Key: kf_live_...
Content-Type: multipart/form-data

file=<binary>
```

### 4. Poll for completion
```
GET /jobs/{job_id}
X-API-Key: kf_live_...
```
Poll every 5–10 seconds until `status` is `"completed"` or `"failed"`.

### 5. Fetch the transcript
```
GET /jobs/{job_id}/result
X-API-Key: kf_live_...
```
Returns a `TranscriptionResult` with full speaker-diarized transcript.

## Authentication
All requests (except POST /keys and GET /health) require:
```
X-API-Key: kf_live_<your-key>
```

## Error Handling
All errors include a machine-readable `code`, `retryable` flag, and `suggested_action`:
```json
{"error": {"code": "UPSTREAM_QUOTA_EXCEEDED", "retryable": true, "retry_after_seconds": 60, "suggested_action": "..."}}
```

## Rate Limits
- Free tier: 5 req/min, 60 audio-minutes/month
- Pro tier: 60 req/min, 1000 audio-minutes/month

## Pricing
- Free: 60 audio-minutes/month included
- Pay-as-you-go: $0.05/audio-minute after free quota
- Check usage: GET /keys/me/usage

## Key Endpoints
- POST /jobs — submit by URL
- POST /jobs/upload — submit by file
- GET /jobs/{id} — poll status
- GET /jobs/{id}/result — fetch TranscriptionResult
- POST /keys — create API key
- GET /keys/me/usage — check quota
- GET /health — liveness check
- GET /openapi.json — full OpenAPI spec

## Full API Reference
- Interactive docs: /docs
- OpenAPI spec: /openapi.json
- ReDoc: /redoc
"""


@router.get(
    "/llms.txt",
    response_class=PlainTextResponse,
    summary="LLMs.txt — agent-readable API overview",
    description="Plain-text summary of this API for AI agents and LLMs, following the llmstxt.org convention.",
    include_in_schema=True,
)
async def llms_txt():
    return PlainTextResponse(LLMS_TXT, media_type="text/plain")


@router.get(
    "/.well-known/ai-plugin.json",
    summary="AI plugin manifest",
    description="ChatGPT-compatible plugin manifest for agent discovery.",
    include_in_schema=True,
)
async def ai_plugin(request: Request):
    base = str(request.base_url).rstrip("/")
    return {
        "schema_version": "v1",
        "name_for_human": "Keyframe Transcription",
        "name_for_model": "keyframe_transcription",
        "description_for_human": "Speaker-diarized video/audio transcription with language detection.",
        "description_for_model": (
            "Transcribes video or audio files with speaker diarization, language detection, "
            "and English translation. Submit a URL or file, poll for completion, fetch the "
            "structured TranscriptionResult. Requires X-API-Key header. "
            "Create a key with POST /keys (no auth needed)."
        ),
        "auth": {
            "type": "service_http",
            "authorization_type": "bearer",
            "verification_tokens": {},
        },
        "api": {
            "type": "openapi",
            "url": f"{base}/openapi.json",
        },
        "logo_url": f"{base}/static/logo.png",
        "contact_email": "api@keyframe.ink",
        "legal_info_url": f"{base}/legal",
    }


@router.get(
    "/.well-known/openapi.yaml",
    summary="OpenAPI spec (alternate well-known path)",
    description="OpenAPI 3.1 spec at the well-known path for automated agent discovery.",
    include_in_schema=False,
)
async def well_known_openapi(request: Request):
    from fastapi.responses import RedirectResponse
    base = str(request.base_url).rstrip("/")
    return RedirectResponse(url=f"{base}/openapi.json")
