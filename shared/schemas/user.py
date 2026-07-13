from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_id: UUID
    theme: Literal["dark", "light"] = "dark"
    language: str = "en"
    hitl_enabled: bool = True
    ai_agent_persona: str = "Professional Educator"
    template_selection: str = "Educational"


class UserSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: Literal["dark", "light"] | None = None
    language: str | None = Field(default=None, max_length=10)
    hitl_enabled: bool | None = None
    ai_agent_persona: str | None = Field(default=None, max_length=100)
    template_selection: str | None = Field(default=None, max_length=100)
