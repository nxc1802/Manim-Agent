from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VoiceSynthesizeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_script_override: str | None = Field(default=None, max_length=20_000)
    language: str = Field(default="vi", min_length=2, max_length=16)


class VoiceEnqueueResponse(BaseModel):
    """TTS runs in a dedicated Celery worker; poll `poll_path` for completion."""

    model_config = ConfigDict(extra="forbid")

    voice_job_id: UUID
    status: Literal["queued"] = "queued"
    poll_path: str = Field(
        min_length=1,
        description="Relative URL, e.g. `/v1/voice-jobs/{voice_job_id}`.",
    )


class VoiceJobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    project_id: UUID
    scene_id: UUID
    status: Literal["queued", "synthesizing", "completed", "failed", "cancelled"]
    progress: int = Field(default=0, ge=0, le=100)
    logs: str | None = None
    asset_url: str | None = Field(
        default=None,
        description="Playback URL (e.g. signed Storage URL) when status is completed.",
    )
    error_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    voice_engine: str = Field(default="piper")
    docker_image_tag: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
