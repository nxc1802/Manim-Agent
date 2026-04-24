from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

StoryboardStatus = Literal["missing", "pending_review", "approved"]
PlanStatus = Literal["missing", "pending_review", "approved"]
VoiceScriptStatus = Literal["missing", "pending_review", "approved"]
ReviewLoopStatus = Literal["idle", "running", "completed", "hitl_pending", "failed"]


class SceneCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_order: int = Field(ge=0)
    storyboard_text: str | None = Field(default=None, max_length=200_000)
    voice_script: str | None = Field(default=None, max_length=200_000)


class Scene(BaseModel):
    """Row shape for `public.scenes`."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    project_id: UUID
    scene_order: int
    storyboard_status: StoryboardStatus = "missing"
    storyboard_text: str | None = None
    voice_script: str | None = None
    planner_output: dict[str, Any] | list[Any] | None = None
    sync_segments: dict[str, Any] | list[Any] | None = None
    manim_code: str | None = None
    manim_code_version: int = 1
    audio_url: str | None = None
    timestamps: dict[str, Any] | list[Any] | None = None
    duration_seconds: Decimal | None = None
    plan_status: PlanStatus = "missing"
    voice_script_status: VoiceScriptStatus = "missing"
    review_loop_status: ReviewLoopStatus = "idle"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="before")
    @classmethod
    def default_scene_row_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            out = dict(data)
            if "storyboard_status" not in out:
                out["storyboard_status"] = "missing"
            if "plan_status" not in out:
                out["plan_status"] = "missing"
            if "voice_script_status" not in out:
                out["voice_script_status"] = "missing"
            if "review_loop_status" not in out:
                out["review_loop_status"] = "idle"
            return out
        return data
