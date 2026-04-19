from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from shared.schemas.review import ReviewResult


class ReviewRoundRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview_job_id: str | None = Field(
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

    preview_poll_timeout_seconds: float | None = Field(
        default=None,
        description="Override preview job poll timeout from runtime_limits YAML.",
    )


class BuilderReviewLoopResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    review_loop_status: str
    report: dict[str, Any] = Field(default_factory=dict)
    rounds: list[dict[str, Any]] = Field(default_factory=list)
