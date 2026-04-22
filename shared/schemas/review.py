from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReviewSeverity = Literal["info", "warning", "error", "blocker"]


class ReviewIssue(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str
    message: str
    severity: ReviewSeverity = "warning"
    line_number: int | None = None
class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    issues: list[ReviewIssue] = Field(default_factory=list)
