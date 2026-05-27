"""Background job runner."""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import pathlib
import uuid

from api.db import get_db
from api.auth import DOCS_BASE


async def _update_job(db, job_id: str, **fields) -> None:
    fields["updated_at"] = datetime.datetime.utcnow().isoformat()
    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [job_id]
    await db.execute(f"UPDATE jobs SET {sets} WHERE id = ?", vals)
    await db.commit()


async def run_pipeline(job_id: str, file_path: str | None, source_url: str | None, api_key_id: str, tier: str, model: str | None) -> None:
    db = await get_db()
    try:
        await _update_job(db, job_id, status="processing")
    finally:
        await db.close()

    try:
        loop = asyncio.get_event_loop()
        from transcribe import transcribe

        result = await loop.run_in_executor(
            None,
            lambda: transcribe(input_path=file_path, url=source_url, model=model),
        )

        audio_minutes = _estimate_audio_minutes(result)
        cost_usd = _calculate_cost(audio_minutes, tier)

        db = await get_db()
        try:
            await _update_job(
                db, job_id,
                status="completed",
                result_json=json.dumps(result),
                audio_minutes=audio_minutes,
            )
            await db.execute(
                "INSERT INTO usage (id, api_key_id, job_id, audio_minutes, cost_usd, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), api_key_id, job_id, audio_minutes, cost_usd, datetime.datetime.utcnow().isoformat()),
            )
            await db.commit()
        finally:
            await db.close()

        # Clean up temp file
        if file_path and os.path.exists(file_path):
            try:
                os.unlink(file_path)
            except OSError:
                pass

    except Exception as exc:
        error_code, error_msg, retryable = _classify_error(exc)
        db = await get_db()
        try:
            await _update_job(
                db, job_id,
                status="failed",
                error_code=error_code,
                error_message=error_msg,
            )
        finally:
            await db.close()

        if file_path and os.path.exists(file_path):
            try:
                os.unlink(file_path)
            except OSError:
                pass


def _estimate_audio_minutes(result: dict) -> float:
    segments = result.get("diarizedTranscript", [])
    if not segments:
        return 0.5  # minimum billing unit
    # Rough estimate: average 3 words/second of speech
    total_words = sum(len(s.get("text", "").split()) for s in segments)
    return max(0.5, total_words / 180.0)  # 180 words/minute


def _calculate_cost(audio_minutes: float, tier: str) -> float:
    from api.pricing import PRICE_PER_MINUTE, QUOTA_MINUTES
    quota = QUOTA_MINUTES.get(tier, 60.0)
    # Cost only applies after free quota is exceeded (simplified: charge all at rate)
    return round(audio_minutes * PRICE_PER_MINUTE, 4)


def _classify_error(exc: Exception) -> tuple[str, str, bool]:
    msg = str(exc).lower()
    if "429" in msg or "rate" in msg or "quota" in msg:
        return ("UPSTREAM_QUOTA_EXCEEDED", "Upstream API quota exceeded. Please retry.", True)
    if "timeout" in msg or "deadline" in msg or "timed out" in msg:
        return ("UPSTREAM_TIMEOUT", "Upstream API timed out.", True)
    if "500" in msg or "503" in msg or "overloaded" in msg:
        return ("UPSTREAM_ERROR", "Upstream service returned an error.", True)
    return ("PIPELINE_ERROR", f"Transcription failed: {exc}", False)
