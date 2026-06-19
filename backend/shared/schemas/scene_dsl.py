from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Position(BaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    relative_to: str | None = None  # e.g., "left_of", "right_of", "above", "below", "to_edge"
    target_id: str | None = None
    buff: float = 0.2


class ThemeConfig(BaseModel):
    primary_color: str = "BLUE"
    secondary_color: str = "GREEN"
    background_color: str = "BLACK"
    font: str | None = None


class CameraState(BaseModel):
    position: tuple[float, float, float] | None = None
    zoom: float | None = None


class TransitionSpec(BaseModel):
    transition_type: str = "fade_out"  # "fade_out", "slide_out"
    duration: float = 1.0


class VisualElement(BaseModel):
    id: str
    type: str  # maps to primitives like "get_text_panel", "get_array_block"
    params: dict[str, Any] = Field(default_factory=dict)
    position: Position | None = None


class AnimationStep(BaseModel):
    target_ids: list[str]
    animation_type: str  # maps to animation primitives like "cinematic_fade_in", "write", "transform"
    params: dict[str, Any] = Field(default_factory=dict)
    run_time: float | None = None
    simultaneous: bool = False


class SceneDSLBeat(BaseModel):
    id: str
    label: str
    duration_seconds: float
    narration: str | None = None
    visual_elements: list[VisualElement] = Field(default_factory=list)
    animations: list[AnimationStep] = Field(default_factory=list)
    camera: CameraState | None = None
    transition_out: TransitionSpec | None = None


class SceneDSL(BaseModel):
    version: str = "1.0"
    title: str
    beats: list[SceneDSLBeat] = Field(default_factory=list)
    global_theme: ThemeConfig | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
