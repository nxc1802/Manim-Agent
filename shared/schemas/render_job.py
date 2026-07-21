from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

RenderJobType = Literal["preview", "full", "full_project"]
RenderJobStatus = Literal["queued", "rendering", "completed", "failed", "cancelled"]
RenderQuality = Literal["480p", "720p", "1080p", "4k"]


class RenderJob(BaseModel):
    """Row shape for `public.render_jobs`."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    project_id: UUID
    scene_id: UUID | None = None
    job_type: RenderJobType
    # Render-job coordination remains ephemeral in Redis for the single-Space profile.
    render_quality: RenderQuality | None = None
    status: RenderJobStatus = "queued"
    progress: int = Field(default=0, ge=0, le=100)
    logs: str | None = None
    asset_url: str | None = None
    error_code: str | None = None
    docker_image_tag: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
