"""API key management endpoints."""

from __future__ import annotations

import datetime
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from api.auth import DOCS_BASE, generate_key, require_api_key, _hash_key
from api.db import get_db
from api.models import KeyCreateRequest, KeyCreateResponse, KeyInfo, UsageResponse
from api.pricing import get_usage

router = APIRouter(prefix="/keys", tags=["API Keys"])


@router.post(
    "",
    summary="Create a new API key",
    description=(
        "Create an API key for authenticating requests. "
        "The full key is returned exactly once — store it securely. "
        "Use the key in the X-API-Key request header."
    ),
    response_model=KeyCreateResponse,
    status_code=201,
)
async def create_key(body: KeyCreateRequest):
    key = generate_key()
    key_id = str(uuid.uuid4())
    now = datetime.datetime.utcnow().isoformat()

    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO api_keys (id, key_hash, name, tier, is_active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
            (key_id, _hash_key(key), body.name, body.tier, now),
        )
        await db.commit()
    finally:
        await db.close()

    return {"id": key_id, "key": key, "name": body.name, "tier": body.tier, "created_at": now}


@router.get(
    "/me",
    summary="List your API keys",
    description="Returns all active API keys for the authenticated key's account (keys are masked).",
    response_model=list[KeyInfo],
)
async def list_keys(key: dict = Depends(require_api_key)):
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT id, name, tier, is_active, created_at FROM api_keys WHERE id = ?",
            (key["id"],),
        )
    finally:
        await db.close()

    return [
        {
            "id": r["id"],
            "name": r["name"],
            "tier": r["tier"],
            "key_preview": "kf_live_" + "***",
            "is_active": bool(r["is_active"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@router.get(
    "/me/usage",
    summary="Get usage and remaining quota",
    description=(
        "Returns current-month usage in minutes, remaining quota, and reset date. "
        "Agents can use this to check available capacity before submitting jobs."
    ),
    response_model=UsageResponse,
)
async def get_my_usage(key: dict = Depends(require_api_key)):
    return await get_usage(key["id"], key["tier"])


@router.delete(
    "/{key_id}",
    summary="Revoke an API key",
    description="Permanently deactivates an API key. This cannot be undone.",
    status_code=204,
)
async def revoke_key(key_id: str, key: dict = Depends(require_api_key)):
    if key_id != key["id"]:
        raise HTTPException(status_code=403, detail={"error": {
            "code": "FORBIDDEN",
            "message": "You can only revoke your own API key.",
            "retryable": False,
            "retry_after_seconds": None,
            "suggested_action": "Use the key_id returned when you created the key.",
            "docs_url": f"{DOCS_BASE}/docs#keys",
        }})

    db = await get_db()
    try:
        await db.execute("UPDATE api_keys SET is_active = 0 WHERE id = ?", (key_id,))
        await db.commit()
    finally:
        await db.close()


@router.get("/new", response_class=HTMLResponse, include_in_schema=False)
async def key_creation_form(request: Request):
    return HTMLResponse("""<!DOCTYPE html>
<html>
<head><title>Create API Key — Keyframe Transcribe</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 480px; margin: 60px auto; padding: 0 20px; color: #111; }
  h1 { font-size: 1.4rem; margin-bottom: 4px; }
  p { color: #555; font-size: 0.9rem; margin-bottom: 24px; }
  label { display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 4px; }
  input, select { width: 100%; padding: 8px 10px; border: 1px solid #ccc; border-radius: 6px; font-size: 0.95rem; box-sizing: border-box; margin-bottom: 16px; }
  button { background: #111; color: #fff; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 0.95rem; }
  button:hover { background: #333; }
  #result { margin-top: 24px; padding: 14px; background: #f5f5f5; border-radius: 8px; display: none; }
  #key-value { font-family: monospace; word-break: break-all; font-size: 0.85rem; background: #fff; padding: 10px; border-radius: 4px; border: 1px solid #ddd; margin-top: 8px; }
  .warning { color: #b45309; font-size: 0.8rem; margin-top: 8px; }
</style>
</head>
<body>
  <h1>Create API Key</h1>
  <p>Keys authenticate requests to the Keyframe Transcription API via the <code>X-API-Key</code> header.</p>
  <form id="form">
    <label for="name">Key name (label for yourself)</label>
    <input id="name" name="name" placeholder="e.g. my-agent" required />
    <label for="tier">Tier</label>
    <select id="tier" name="tier">
      <option value="free">Free — 60 min/month</option>
      <option value="pro">Pro — 1000 min/month ($0.05/min)</option>
    </select>
    <button type="submit">Create Key</button>
  </form>
  <div id="result">
    <strong>Your API key (shown once — save it now):</strong>
    <div id="key-value"></div>
    <p class="warning">⚠ This key will not be shown again. Copy it now.</p>
  </div>
  <script>
    document.getElementById('form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const res = await fetch('/keys', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: document.getElementById('name').value, tier: document.getElementById('tier').value})
      });
      const data = await res.json();
      document.getElementById('key-value').textContent = data.key;
      document.getElementById('result').style.display = 'block';
    });
  </script>
</body>
</html>""")
