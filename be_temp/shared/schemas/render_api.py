from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from shared.schemas.render_job import RenderQuality


class RenderEnqueueBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    render_type: Literal["preview", "full"] = "preview"
    quality: RenderQuality = "720p"
    webhook_url: HttpUrl | None = None
    scene_id: UUID | None = Field(
        default=None,
        description="When set, worker renders `manim_code` from this scene (class GeneratedScene).",
    )


class RenderEnqueueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    status: Literal["queued"] = "queued"


class RenderJobStatusResponse(BaseModel):
    """`RenderJob` fields exposed by `GET /v1/jobs/{job_id}`."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    project_id: UUID
    scene_id: UUID | None = Field(
        default=None,
        description="Source scene when render was enqueued with scene_id.",
    )
    job_type: Literal["preview", "full"]
    render_quality: RenderQuality | None = None
    status: Literal["queued", "rendering", "completed", "failed", "cancelled"]
    progress: int = Field(default=0, ge=0, le=100)
    logs: str | None = None
    asset_url: str | None = None
    error_code: str | None = None
    webhook_url: str | None = None
    docker_image_tag: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
