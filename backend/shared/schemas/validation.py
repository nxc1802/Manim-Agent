from __future__ import annotations

from pydantic import BaseModel

from shared.constants import SeverityLevel


class ValidationIssue(BaseModel):
    code: str  # e.g., "tex_usage", "missing_construct"
    severity: SeverityLevel
    message: str
    line: int | None = None
    suggestion: str | None = None
    auto_fixable: bool = False


class ValidationResult(BaseModel):
    passed: bool
    issues: list[ValidationIssue]
