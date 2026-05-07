from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

StoryboardStatus = Literal["missing", "pending_review", "approved"]
PlanStatus = Literal["missing", "pending_review", "approved"]
VoiceScriptStatus = Literal["missing", "pending_review", "approved"]
ReviewLoopStatus = Literal["idle", "running", "completed", "hitl_pending", "failed"]


class SceneCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_order: int = Field(ge=0, description="Thứ tự của scene trong video (0-indexed)")
    storyboard_text: str | None = Field(
        default=None, max_length=20_000, description="Nội dung storyboard (draft)"
    )
    voice_script: str | None = Field(
        default=None, max_length=200_000, description="Kịch bản lời thoại (voiceover)"
    )


class SceneUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_order: int | None = Field(default=None, ge=0)
    storyboard_text: str | None = None
    voice_script: str | None = None
    storyboard_status: StoryboardStatus | None = None
    plan_status: PlanStatus | None = None
    voice_script_status: VoiceScriptStatus | None = None
    review_loop_status: ReviewLoopStatus | None = None
    manim_code: str | None = None


class Scene(BaseModel):
    """Row shape for `public.scenes`."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    project_id: UUID
    scene_order: int
    storyboard_status: StoryboardStatus = Field(
        default="missing",
        description="Trạng thái storyboard (missing, pending_review, approved)",
    )
    storyboard_text: str | None = Field(default=None, description="Nội dung storyboard (draft)")
    voice_script: str | None = Field(default=None, description="Kịch bản lời thoại (voiceover)")
    planner_output: dict[str, Any] | list[Any] | None = Field(
        default=None, description="Kết quả từ Planner Agent (beats, primitives)"
    )
    sync_segments: dict[str, Any] | list[Any] | None = Field(
        default=None, description="Dữ liệu đồng bộ beat với audio timeline"
    )
    manim_code: str | None = Field(
        default=None, description="Mã nguồn Manim Python được sinh bởi Builder Agent"
    )
    manim_code_version: int = Field(default=1, description="Phiên bản của mã nguồn Manim")
    audio_url: str | None = Field(default=None, description="Đường dẫn đến file âm thanh (TTS)")
    timestamps: dict[str, Any] | list[Any] | None = Field(
        default=None, description="Dữ liệu thời gian của từng segment âm thanh"
    )
    duration_seconds: Decimal | None = Field(default=None, description="Tổng thời lượng của scene")
    plan_status: PlanStatus = Field(default="missing", description="Trạng thái của execution plan")
    voice_script_status: VoiceScriptStatus = Field(
        default="missing", description="Trạng thái của voice script"
    )
    review_loop_status: ReviewLoopStatus = Field(
        default="idle",
        description="Trạng thái vòng lặp review (idle, running, completed, hitl_pending, failed)",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

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


class SceneCodeHistory(BaseModel):
    """Row shape for `public.scene_code_history`."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    scene_id: UUID
    run_id: UUID | None = None
    version: int
    round_idx: int | None = None
    manim_code: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
