from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

GenerationModel = Literal[
    "gemini-3-flash-preview",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemma-4-31b-it",
    "gemma-4-26b-it",
    "gemma-4-31b-it-thinking",
    "gemma-4-26b-it-thinking"
]
GenerationAgent = Literal[
    "idea_sketcher",
    "storyboarder",
    "builder",
    "code_reviewer",
    "visual_reviewer",
]
ReasoningEffort = Literal["none", "minimal", "low", "medium", "high"]
TtsVoice = Literal[
    "auto",
    "vi-VN-female",
    "vi-VN-male",
    "en-US-female",
    "en-US-male",
    "vi-VN-Standard-A",
    "vi-VN-Standard-B",
    "en-US-Standard-C",
    "en-US-Standard-D",
]


class AgentLlmConfig(BaseModel):
    """Optional overrides for exactly one configured AI agent."""

    model_config = ConfigDict(extra="forbid")

    model: GenerationModel | None = None
    temperature: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1024, le=16384)
    reasoning_effort: ReasoningEffort | None = None
    review_tiers: list[ReviewTierConfig] | None = Field(
        default=None, min_length=1, max_length=3
    )

    @model_validator(mode="after")
    def _review_tiers_must_not_repeat_models(self) -> AgentLlmConfig:
        if self.review_tiers and len({tier.model for tier in self.review_tiers}) != len(
            self.review_tiers
        ):
            raise ValueError("Review tiers must not repeat the same model")
        return self


class ReviewTierConfig(BaseModel):
    """One explicitly ordered reviewer escalation tier."""

    model_config = ConfigDict(extra="forbid")

    model: GenerationModel
    max_attempts: int = Field(ge=1, le=5)
    reasoning_effort: ReasoningEffort = "none"


class UserSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_id: UUID
    theme: Literal["dark", "light"] = "dark"
    language: Literal["vi", "en"] = "en"
    hitl_enabled: bool = True
    ai_agent_persona: Literal[
        "Professional Educator", "Creative Storyteller", "Technical Explainer"
    ] = "Professional Educator"
    template_selection: Literal[
        "Educational", "Conceptual walkthrough", "Worked example"
    ] = "Educational"

    visual_review_enabled: bool = True
    code_review_enabled: bool = True
    max_review_attempts: int = Field(default=3, ge=1, le=5)

    video_quality: Literal["480p", "720p", "1080p", "4k"] = "720p"
    fps: Literal[15, 30, 60] = 30

    # ``None`` deliberately preserves the per-agent defaults in
    # ``agent_models.yaml``. Values are limited to models currently configured
    # by the AI worker, rather than accepting arbitrary provider model names.
    llm_model: GenerationModel | None = None
    llm_temperature: float | None = Field(default=None, ge=0, le=1)
    llm_max_tokens: int | None = Field(default=None, ge=1024, le=16384)
    llm_agent_configs: dict[GenerationAgent, AgentLlmConfig] = Field(default_factory=dict)

    tts_enabled: bool = False
    tts_voice: TtsVoice = "auto"
    tts_speaking_rate: float = Field(default=1, ge=0.25, le=2)
    tts_pitch: float = Field(default=0, ge=-20, le=20)


class UserSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: Literal["dark", "light"] | None = None
    language: Literal["vi", "en"] | None = None
    hitl_enabled: bool | None = None
    ai_agent_persona: Literal[
        "Professional Educator", "Creative Storyteller", "Technical Explainer"
    ] | None = None
    template_selection: Literal[
        "Educational", "Conceptual walkthrough", "Worked example"
    ] | None = None
    visual_review_enabled: bool | None = None
    code_review_enabled: bool | None = None
    max_review_attempts: int | None = Field(default=None, ge=1, le=5)
    video_quality: Literal["480p", "720p", "1080p", "4k"] | None = None
    fps: Literal[15, 30, 60] | None = None
    llm_model: GenerationModel | None = None
    llm_temperature: float | None = Field(default=None, ge=0, le=1)
    llm_max_tokens: int | None = Field(default=None, ge=1024, le=16384)
    llm_agent_configs: dict[GenerationAgent, AgentLlmConfig] | None = None
    tts_enabled: bool | None = None
    tts_voice: TtsVoice | None = None
    tts_speaking_rate: float | None = Field(default=None, ge=0.25, le=2)
    tts_pitch: float | None = Field(default=None, ge=-20, le=20)
