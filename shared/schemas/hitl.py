"""The only cross-service contract for the human-in-the-loop pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

AgentStepKind = Literal[
    "idea_sketcher",
    "storyboarder",
    "builder",
    "code_reviewer",
    "visual_reviewer",
]
RunStatus = Literal["queued", "waiting_for_human", "completed", "failed", "cancelled"]
StepStatus = Literal[
    "queued",
    "generating",
    "pending_review",
    "approved",
    "rejected",
    "failed",
]


class AiRun(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    project_id: UUID
    scene_id: UUID | None = None
    user_id: UUID
    status: RunStatus
    hitl_enabled: bool = Field(default=True)
    created_at: datetime
    updated_at: datetime


class AgentStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    run_id: UUID
    project_id: UUID
    scene_id: UUID | None = None
    sequence: int = Field(ge=1)
    kind: AgentStepKind
    status: StepStatus
    input: dict[str, Any] = Field(default_factory=dict)
    draft_output: dict[str, Any] | None = None
    final_output: dict[str, Any] | None = None
    revision: int = Field(ge=1)
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class StartAiRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: UUID
    brief_override: str | None = Field(default=None, max_length=20_000)
    hitl_enabled: bool = Field(
        default=True,
        description="When False, all steps auto-approve (testing mode). "
                    "When True, storyboarder requires human review; idea sketching auto-advances.",
    )


class StartProjectRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=20_000)
    hitl_enabled: bool = Field(default=True)


class StartAiRunResponse(BaseModel):
    run: AiRun
    first_step: AgentStep


class EditStepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    draft_output: dict[str, Any]


class ApproveStepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    final_output: dict[str, Any] | None = None


class RejectStepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    feedback: str = Field(min_length=1, max_length=20_000)


class StepTransitionResponse(BaseModel):
    step: AgentStep
    next_step: AgentStep | None = None


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_step_id: UUID


class InternalStepCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_output: dict[str, Any]


class InternalStepFailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: str = Field(min_length=1, max_length=4_000)


# ---------------------------------------------------------------------------
# Review-loop result models (used by code_reviewer & visual_reviewer)
# ---------------------------------------------------------------------------

class ReviewIterationRecord(BaseModel):
    """One iteration inside the code/visual review self-loop."""
    model_config = ConfigDict(extra="forbid")
    iteration: int
    model: str
    error_summary: str | None = None
    fix_applied: str | None = None
    original_code: str | None = None
    replacement_code: str | None = None
    same_error: bool = False
    escalated: bool = False
    error_fingerprint: str | None = None
    strategy_fingerprint: str | None = None
    strategy_guard_triggered: bool = False
    strategy_guard_reason: str | None = None
    repair_history_count: int = 0
    runtime_api_context: dict[str, Any] | None = None
    outcome: str | None = None


class ReviewLoopResult(BaseModel):
    """Output of a review self-loop (code or visual)."""
    model_config = ConfigDict(extra="forbid")
    passed: bool
    manim_code: str
    iterations: list[ReviewIterationRecord] = Field(default_factory=list)
    total_attempts: int = 0
    final_error: str | None = None
