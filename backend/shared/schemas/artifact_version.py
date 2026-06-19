from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ArtifactVersion(BaseModel):
    """Schema representing a version of an artifact (storyboard, dsl, code, plan, etc.)."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    entity_type: str = Field(description="storyboard, plan, dsl, code, or render")
    entity_id: UUID = Field(description="ID of the referenced entity (typically scene_id)")
    version: int = Field(description="Auto-incremented version number for this entity")
    content_hash: str = Field(description="SHA-256 hash of the content for quick comparison")
    content: Any = Field(description="JSON blob representing the state of the entity at this version")
    parent_version: int | None = Field(default=None, description="Previous version number this was branched/modified from")
    created_by: str = Field(description="Who created this version (e.g. planner, user_edit, repair)")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
