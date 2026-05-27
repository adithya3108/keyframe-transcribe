"""Quota and pricing logic."""

from __future__ import annotations

import datetime
from fastapi import HTTPException, status

from api.db import get_db
from api.auth import DOCS_BASE

QUOTA_MINUTES = {"free": 60.0, "pro": 1000.0}
PRICE_PER_MINUTE = 0.05  # USD, after free quota


def _month_reset_date() -> str:
    today = datetime.date.today()
    if today.month == 12:
        return datetime.date(today.year + 1, 1, 1).isoformat()
    return datetime.date(today.year, today.month + 1, 1).isoformat()


def _month_start() -> str:
    today = datetime.date.today()
    return datetime.date(today.year, today.month, 1).isoformat()


async def get_usage(api_key_id: str, tier: str) -> dict:
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT COALESCE(SUM(audio_minutes), 0) as total, COALESCE(SUM(cost_usd), 0) as cost "
            "FROM usage WHERE api_key_id = ? AND created_at >= ?",
            (api_key_id, _month_start()),
        )
    finally:
        await db.close()

    used = float(rows[0]["total"]) if rows else 0.0
    cost = float(rows[0]["cost"]) if rows else 0.0
    quota = QUOTA_MINUTES.get(tier, 60.0)
    return {
        "api_key_id": api_key_id,
        "tier": tier,
        "used_minutes": round(used, 2),
        "quota_minutes": quota,
        "remaining_minutes": round(max(0.0, quota - used), 2),
        "reset_date": _month_reset_date(),
        "cost_usd": round(cost, 4),
    }


async def check_and_reserve_quota(api_key_id: str, tier: str) -> None:
    """Raise 429 if the key has exceeded its monthly quota."""
    usage = await get_usage(api_key_id, tier)
    if usage["remaining_minutes"] <= 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": {
                    "code": "QUOTA_EXCEEDED",
                    "message": f"Monthly quota of {usage['quota_minutes']} minutes exhausted.",
                    "retryable": False,
                    "retry_after_seconds": None,
                    "suggested_action": f"Quota resets on {usage['reset_date']}. Upgrade to 'pro' tier for higher limits.",
                    "docs_url": f"{DOCS_BASE}/docs#pricing",
                }
            },
        )
