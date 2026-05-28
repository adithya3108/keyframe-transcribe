"""API-layer Pydantic models."""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class JobSubmitURL(BaseModel):
    url: str = Field(..., description="Public URL of the video/audio file to transcribe (max 100MB).")
    model: Optional[str] = Field(None, description="Force a specific Gemini model. Omit to use the default (gemini-2.5-flash with Pro fallback).", json_schema_extra={"example": None})


class JobStatusResponse(BaseModel):
    job_id: str = Field(..., description="Unique job identifier.")
    status: Literal["queued", "processing", "completed", "failed"] = Field(..., description="Current job status.")
    poll_url: str = Field(..., description="URL to poll for status updates.")
    result_url: Optional[str] = Field(None, description="URL to fetch the full result. Only present when status is 'completed'.")
    error: Optional["ErrorDetail"] = Field(None, description="Error details. Only present when status is 'failed'.")
    created_at: str
    updated_at: str


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code.")
    message: str = Field(..., description="Human-readable error description.")
    retryable: bool = Field(..., description="Whether the caller should retry this request.")
    retry_after_seconds: Optional[int] = Field(None, description="Suggested wait time before retrying.")
    suggested_action: str = Field(..., description="What the agent/caller should do next.")
    docs_url: str = Field(..., description="Link to relevant documentation.")


class ErrorResponse(BaseModel):
    error: ErrorDetail


class KeyCreateRequest(BaseModel):
    name: str = Field(..., description="Human-readable label for this API key.", min_length=1, max_length=100)
    tier: Literal["free", "pro"] = Field("free", description="Service tier. 'free' = 60 min/month. 'pro' = 1000 min/month at $0.05/min.")


class KeyCreateResponse(BaseModel):
    id: str
    key: str = Field(..., description="Full API key — shown exactly ONCE. Store it securely.")
    name: str
    tier: str
    created_at: str


class KeyInfo(BaseModel):
    id: str
    name: str
    tier: str
    key_preview: str = Field(..., description="First 12 characters of the key followed by ***.")
    is_active: bool
    created_at: str


class UsageResponse(BaseModel):
    api_key_id: str
    tier: str
    used_minutes: float
    quota_minutes: float
    remaining_minutes: float
    reset_date: str
    cost_usd: float


JobStatusResponse.model_rebuild()
