from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ProjectStatus = Literal["draft", "processing", "completed", "archived"]


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=20_000)
    source_language: str = Field(default="vi", min_length=2, max_length=16)


class Project(BaseModel):
    """Row shape for `public.projects` (see docs/proposal/09_supabase_schema.md)."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    user_id: UUID
    title: str
    description: str | None = None
    source_language: str = "vi"
    config: dict[str, Any] = Field(default_factory=dict)
    status: ProjectStatus = "draft"
    created_at: datetime
    updated_at: datetime
