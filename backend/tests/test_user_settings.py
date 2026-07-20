from __future__ import annotations

import pytest
from pydantic import ValidationError
from shared.schemas.user import UserSettingsUpdate


def test_supported_settings_are_validated_by_the_backend_contract() -> None:
    update = UserSettingsUpdate(
        language="vi",
        ai_agent_persona="Technical Explainer",
        template_selection="Worked example",
        code_review_enabled=True,
        visual_review_enabled=False,
        max_review_attempts=2,
        video_quality="1080p",
        fps=60,
        llm_model="gemini-3.5-flash",
        llm_temperature=0.3,
        llm_max_tokens=8192,
        llm_agent_configs={
            "idea_sketcher": {
                "model": "gemini-3-flash-preview",
                "reasoning_effort": "low",
                "max_tokens": 4096,
            },
            "builder": {
                "model": "gemini-3.5-flash",
                "temperature": 0.1,
                "max_tokens": 8192,
                "reasoning_effort": "high",
            },
            "code_reviewer": {
                "review_tiers": [
                    {"model": "gemma-4-31b-it", "max_attempts": 1, "reasoning_effort": "none"},
                    {"model": "gemini-3-flash-preview", "max_attempts": 2, "reasoning_effort": "medium"},
                ]
            },
        },
        tts_enabled=True,
        tts_voice="vi-VN-Standard-A",
        tts_speaking_rate=1.25,
        tts_pitch=2,
    )

    assert update.model_dump(exclude_unset=True) == {
        "language": "vi",
        "ai_agent_persona": "Technical Explainer",
        "template_selection": "Worked example",
        "code_review_enabled": True,
        "visual_review_enabled": False,
        "max_review_attempts": 2,
        "video_quality": "1080p",
        "fps": 60,
        "llm_model": "gemini-3.5-flash",
        "llm_temperature": 0.3,
        "llm_max_tokens": 8192,
        "llm_agent_configs": {
            "idea_sketcher": {
                "model": "gemini-3-flash-preview",
                "max_tokens": 4096,
                "reasoning_effort": "low",
            },
            "builder": {
                "model": "gemini-3.5-flash",
                "temperature": 0.1,
                "max_tokens": 8192,
                "reasoning_effort": "high",
            },
            "code_reviewer": {
                "review_tiers": [
                    {"model": "gemma-4-31b-it", "max_attempts": 1, "reasoning_effort": "none"},
                    {"model": "gemini-3-flash-preview", "max_attempts": 2, "reasoning_effort": "medium"},
                ]
            },
        },
        "tts_enabled": True,
        "tts_voice": "vi-VN-Standard-A",
        "tts_speaking_rate": 1.25,
        "tts_pitch": 2.0,
    }


def test_legacy_nonfunctional_setting_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UserSettingsUpdate.model_validate({"builder_model": "made-up-model"})


def test_agent_model_config_rejects_unknown_agents_and_models() -> None:
    with pytest.raises(ValidationError):
        UserSettingsUpdate.model_validate(
            {"llm_agent_configs": {"invented_agent": {"model": "gemini-3-flash-preview"}}}
        )
    with pytest.raises(ValidationError):
        UserSettingsUpdate.model_validate(
            {"llm_agent_configs": {"builder": {"model": "invented-model"}}}
        )
    with pytest.raises(ValidationError):
        UserSettingsUpdate.model_validate(
            {
                "llm_agent_configs": {
                    "code_reviewer": {
                        "review_tiers": [
                            {"model": "gemma-4-31b-it", "max_attempts": 1},
                            {"model": "gemma-4-31b-it", "max_attempts": 1},
                        ]
                    }
                }
            }
        )
