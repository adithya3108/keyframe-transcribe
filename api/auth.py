"""API key authentication and middleware."""

from __future__ import annotations

import hashlib
import secrets
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from api.db import get_db

_header = APIKeyHeader(name="X-API-Key", auto_error=False)

DOCS_BASE = "https://keyframe-transcribe.onrender.com"


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_key() -> str:
    return "kf_live_" + secrets.token_urlsafe(32)


async def require_api_key(api_key: str = Security(_header)) -> dict:
    """FastAPI dependency: validate X-API-Key header and return the key row."""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "MISSING_API_KEY",
                    "message": "No API key provided.",
                    "retryable": False,
                    "retry_after_seconds": None,
                    "suggested_action": "Include your API key in the X-API-Key request header.",
                    "docs_url": f"{DOCS_BASE}/docs#authentication",
                }
            },
        )

    key_hash = _hash_key(api_key)
    db = await get_db()
    try:
        row = await db.execute_fetchall(
            "SELECT id, name, tier, is_active FROM api_keys WHERE key_hash = ?",
            (key_hash,),
        )
    finally:
        await db.close()

    if not row or not row[0]["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_API_KEY",
                    "message": "API key is invalid or has been revoked.",
                    "retryable": False,
                    "retry_after_seconds": None,
                    "suggested_action": "Create a new API key at POST /keys.",
                    "docs_url": f"{DOCS_BASE}/docs#authentication",
                }
            },
        )

    return dict(row[0])
