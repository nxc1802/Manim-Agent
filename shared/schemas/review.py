from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReviewSeverity = Literal["info", "warning", "error", "blocker"]


class ReviewIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: ReviewSeverity = "warning"
    code: str = Field(default="generic", min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=8000)
    location: str | None = Field(default=None, max_length=1024)
    suggestion: str | None = Field(default=None, max_length=8000)


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issues: list[ReviewIssue] = Field(default_factory=list)
