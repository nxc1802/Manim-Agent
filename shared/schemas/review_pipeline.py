from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from shared.schemas.review import ReviewResult
from shared.schemas.scene import Scene


class ReviewRoundRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview_job_id: UUID | None = Field(
        default=None,
        description="Completed render job whose asset is a local file:// preview mp4 (dev/CI).",
    )


class ReviewRoundResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    static_parse_ok: bool
    static_imports_ok: bool
    code_review: ReviewResult
    code_review_passed: bool
    visual_review: ReviewResult | None = None
    visual_review_skipped_reason: str | None = None
    visual_review_passed: bool | None = None
    early_stop: bool = Field(
        description="True only when both code_review_passed and visual_review_passed are true.",
    )
    metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Per-agent timings/tokens, e.g. code_reviewer / visual_reviewer.",
    )


class BuilderReviewLoopRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["auto", "hitl"] = Field(
        default="hitl",
        description="Dual mode: 'auto' for straight approval/fail, 'hitl' for manual gates on failure.",
    )
    preview_poll_timeout_seconds: float | None = Field(
        default=None,
        description="Override preview job poll timeout from runtime_limits YAML.",
    )


class HitlReviewLoopAckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["revert", "continue", "stop"]
    extra_rounds: int | None = Field(default=None, ge=1, le=10)


class HitlReviewLoopAckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene: Scene
    message: str | None = None


class BuilderReviewLoopResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: UUID
    review_loop_status: str
    report: dict[str, Any] = Field(default_factory=dict)
    rounds: list[dict[str, Any]] = Field(default_factory=list)
