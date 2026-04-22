from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PrimitiveCall(BaseModel):
    """Single primitive invocation planned for a beat."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=256)
    args: dict[str, Any] = Field(default_factory=dict)


class TimelineBeat(BaseModel):
    """One narrative/visual beat mapped to optional Manim `step_n` label."""

    model_config = ConfigDict(extra="ignore")

    step_label: str = Field(min_length=1, max_length=256)
    narration_hint: str = Field(default="", max_length=20_000)
    primitives: list[PrimitiveCall] = Field(default_factory=list)


class PlannerOutput(BaseModel):
    """Structured plan from Planner (C4a) for Builder / sync (contract v1)."""

    model_config = ConfigDict(extra="ignore", coerce_numbers_to_str=True)

    version: str = Field(default="1", pattern="^1$")
    beats: list[TimelineBeat] = Field(min_length=1)
