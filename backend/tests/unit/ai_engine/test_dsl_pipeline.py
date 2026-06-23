from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from ai_engine.builder_loop import run_builder_loop_phase
from ai_engine.config import RuntimeLimitsConfig
from shared.schemas.review import ReviewResult
from shared.schemas.review_pipeline import ReviewRoundResponse
from shared.schemas.scene import Scene


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def mock_runtime_limits() -> RuntimeLimitsConfig:
    return RuntimeLimitsConfig(
        worker_man_render_timeout_seconds=3600,
        worker_tts_subprocess_timeout_seconds=900,
        preview_poll_timeout_seconds=900,
        preview_poll_interval_seconds=0.1,
        llm_timeout_default_seconds=600,
        llm_timeouts={},
    )


@pytest.fixture()
def mock_scene() -> Scene:
    return Scene(
        id=uuid4(),
        project_id=uuid4(),
        scene_order=0,
        storyboard_text="test storyboard",
        voice_script="test voice script",
        planner_output={
            "version": "1",
            "beats": [{"step_label": "intro", "narration_hint": "hello", "primitives": []}],
        },
        manim_code="",
        manim_code_version=0,
    )


@pytest.mark.anyio
@patch("ai_engine.builder_loop.run_scene_designer", new_callable=AsyncMock)
@patch("ai_engine.builder_loop.wait_for_render_job")
@patch("ai_engine.builder_loop.run_single_review_round_ex", new_callable=AsyncMock)
@patch("ai_engine.builder_loop.render_manim_scene")
async def test_dsl_pipeline_success(
    mock_render_task: MagicMock,
    mock_review_round: AsyncMock,
    mock_wait_job: MagicMock,
    mock_scene_designer: AsyncMock,
    mock_scene: Scene,
    mock_runtime_limits: RuntimeLimitsConfig,
) -> None:
    # Setup mocks
    store = MagicMock()
    store.get_scene.return_value = mock_scene

    # Mock dynamic updates to scene object
    def update_scene_side_effect(scene_id: Any, **kwargs: Any) -> Scene:
        for k, v in kwargs.items():
            setattr(mock_scene, k, v)
        return mock_scene

    store.update_scene.side_effect = update_scene_side_effect

    job_store = MagicMock()
    llm = MagicMock()

    dsl_code = """
from shared.schemas.scene_dsl import (
    AnimationStep, Position, SceneDSLBeat, ThemeConfig, VisualElement
)

class GeneratedSceneDSL:
    title = "Test DSL Scene"
    global_theme = ThemeConfig(primary_color="BLUE")
    beats = [
        SceneDSLBeat(
            id="beat_1",
            label="Intro Beat",
            duration_seconds=2.0,
            visual_elements=[
                VisualElement(
                    id="title",
                    type="get_title_card",
                    params={"title": "Test Title"},
                    position=Position(x=0.0, y=0.0)
                )
            ],
            animations=[
                AnimationStep(
                    target_ids=["title"],
                    animation_type="cinematic_fade_in",
                    run_time=1.0
                )
            ]
        )
    ]
"""
    mock_scene_designer.return_value = (
        dsl_code,
        "dsl_v1",
        {"duration_ms": 100},
        "sys",
        "usr",
    )

    job_mock = MagicMock()
    job_mock.status = "completed"
    job_mock.asset_url = "file:///tmp/x.mp4"
    job_mock.metadata = {"video_duration": 1.0}
    mock_wait_job.return_value = job_mock

    mock_review_round.return_value = (
        ReviewRoundResponse(
            static_parse_ok=True,
            static_imports_ok=True,
            code_review=ReviewResult(issues=[]),
            code_review_passed=True,
            visual_review_passed=True,
            early_stop=True,
            metrics={},
        ),
        {"code_reviewer": {"system": "s", "user": "u"}},
    )

    scene_out, report = await run_builder_loop_phase(
        scene_id=mock_scene.id,
        store=store,
        job_store=job_store,
        llm=llm,
        yaml_data={"builder_review_loop": {"use_dsl_pipeline": True}},
        runtime_limits=mock_runtime_limits,
        preview_poll_timeout_seconds=10,
    )

    assert report["final_status"] == "completed"
    assert mock_scene_designer.call_count == 1
    # Check database calls
    store.update_scene.assert_any_call(
        mock_scene.id,
        scene_dsl={
            "version": "1.0",
            "title": "Test DSL Scene",
            "global_theme": {
                "primary_color": "BLUE",
                "secondary_color": "GREEN",
                "background_color": "BLACK",
                "font": None,
            },
            "beats": [
                {
                    "id": "beat_1",
                    "label": "Intro Beat",
                    "duration_seconds": 2.0,
                    "narration": None,
                    "visual_elements": [
                        {
                            "id": "title",
                            "type": "get_title_card",
                            "params": {"title": "Test Title"},
                            "position": {
                                "x": 0.0,
                                "y": 0.0,
                                "z": 0.0,
                                "relative_to": None,
                                "target_id": None,
                                "buff": 0.2,
                            },
                        }
                    ],
                    "animations": [
                        {
                            "target_ids": ["title"],
                            "animation_type": "cinematic_fade_in",
                            "params": {},
                            "run_time": 1.0,
                            "simultaneous": False,
                        }
                    ],
                    "camera": None,
                    "transition_out": None,
                }
            ],
            "metadata": {},
        },
        scene_dsl_version=1,
    )
