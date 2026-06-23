from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

DslIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=100)]


class DslModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Position(DslModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    relative_to: str | None = None  # e.g., "left_of", "right_of", "above", "below", "to_edge"
    target_id: str | None = None
    buff: float = 0.2


class ThemeConfig(DslModel):
    primary_color: str = "BLUE"
    secondary_color: str = "GREEN"
    background_color: str = "BLACK"
    font: str | None = None


class CameraState(DslModel):
    position: tuple[float, float, float] | None = None
    zoom: float | None = None


class TransitionSpec(DslModel):
    transition_type: str = "fade_out"  # "fade_out", "slide_out"
    duration: float = 1.0


class VisualElement(DslModel):
    id: DslIdentifier
    type: DslIdentifier  # maps to primitives like "get_text_panel", "get_array_block"
    params: dict[str, Any] = Field(default_factory=dict)
    position: Position | None = None


class AnimationStep(DslModel):
    target_ids: list[DslIdentifier]
    animation_type: DslIdentifier
    params: dict[str, Any] = Field(default_factory=dict)
    run_time: float | None = None
    simultaneous: bool = False


class SceneDSLBeat(DslModel):
    id: DslIdentifier
    label: str
    duration_seconds: float = Field(gt=0, le=3600)
    narration: str | None = None
    visual_elements: list[VisualElement] = Field(default_factory=list)
    animations: list[AnimationStep] = Field(default_factory=list)
    camera: CameraState | None = None
    transition_out: TransitionSpec | None = None


class SceneDSL(DslModel):
    version: str = "1.0"
    title: str
    beats: list[SceneDSLBeat] = Field(default_factory=list)
    global_theme: ThemeConfig | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> SceneDSL:
        beat_ids: set[str] = set()
        known_elements: set[str] = set()
        for beat in self.beats:
            if beat.id in beat_ids:
                raise ValueError(f"Duplicate beat id: {beat.id}")
            beat_ids.add(beat.id)
            for element in beat.visual_elements:
                if element.id in known_elements:
                    raise ValueError(f"Duplicate visual element id: {element.id}")
                if element.position and element.position.target_id:
                    if element.position.target_id not in known_elements:
                        raise ValueError(
                            f"Unknown position target_id: {element.position.target_id}"
                        )
                known_elements.add(element.id)
            for animation in beat.animations:
                missing = set(animation.target_ids) - known_elements
                if missing:
                    raise ValueError(f"Unknown animation target ids: {sorted(missing)}")
        return self
