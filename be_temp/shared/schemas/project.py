from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ProjectStatus = Literal["draft", "processing", "completed", "archived"]


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        min_length=1,
        max_length=500,
        description="Tiêu đề của dự án (ví dụ: Giải thuật Binary Search)",
        examples=["Binary Search Visualization"],
    )
    description: str | None = Field(
        default=None,
        max_length=20_000,
        description="Mô tả chi tiết về nội dung hoặc mục tiêu của video",
        examples=["Giải thích cách hoạt động của Binary Search qua ví dụ cụ thể"],
    )
    source_language: str = Field(
        default="vi",
        min_length=2,
        max_length=16,
        description="Ngôn ngữ nguồn (vi, en, ...)",
        examples=["vi"],
    )
    target_scenes: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Số lượng scene mục tiêu (Director sẽ cố gắng bám sát con số này)",
        examples=[3],
    )
    use_primitives: bool = Field(
        default=True,
        description="Sử dụng các component (primitives) có sẵn hay viết code từ đầu",
    )
    config: dict[str, Any] | None = Field(
        default=None,
        description="Cấu hình bổ sung cho project (ví dụ: model_params, feature_toggles)",
    )


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=20_000)
    source_language: str | None = Field(default=None, min_length=2, max_length=16)
    target_scenes: int | None = Field(default=None, ge=1, le=20)
    status: ProjectStatus | None = None
    config: dict[str, Any] | None = None


class Project(BaseModel):
    """Row shape for `public.projects` (see docs/proposal/09_supabase_schema.md)."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    user_id: UUID
    title: str
    description: str | None = None
    source_language: str = "vi"
    target_scenes: int | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    status: ProjectStatus = "draft"
    created_at: datetime
    updated_at: datetime
