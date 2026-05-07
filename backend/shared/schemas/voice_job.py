from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

VoiceJobStatus = Literal["queued", "synthesizing", "completed", "failed", "cancelled"]


class VoiceJob(BaseModel):
    """TTS job persisted in Redis (and optionally mirrored to Postgres `voice_jobs`)."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    project_id: UUID
    scene_id: UUID
    status: VoiceJobStatus = "queued"
    progress: int = Field(default=0, ge=0, le=100)
    logs: str | None = None
    asset_url: str | None = None
    error_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    voice_engine: str = Field(default="piper", min_length=1, max_length=64)
    docker_image_tag: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
