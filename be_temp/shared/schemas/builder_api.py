from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from shared.schemas.scene import Scene


class GenerateCodeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enqueue_preview: bool = Field(
        default=False,
        description="If true, enqueue a preview render job using this scene's manim_code.",
    )


class GenerateCodeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene: Scene
    preview_job_id: UUID | None = None
