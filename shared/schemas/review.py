from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from shared.constants import SeverityLevel

ReviewSeverity = SeverityLevel


class ReviewIssue(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str
    message: str
    severity: ReviewSeverity = SeverityLevel.WARNING
    line_number: int | None = None
    suggestion: str | None = Field(
        default=None, description="Optional code snippet or instruction to fix the issue"
    )


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    issues: list[ReviewIssue] = Field(default_factory=list)
