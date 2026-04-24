from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from ai_engine.orchestrator import run_builder_loop_phase
from ai_engine.config import RuntimeLimitsConfig
from shared.schemas.scene import Scene
from shared.schemas.review_pipeline import ReviewRoundResponse
from shared.schemas.review import ReviewResult


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
            "beats": [{"step_label": "intro", "narration_hint": "hello", "primitives": []}]
        },
        manim_code="",
        manim_code_version=0,
    )


@patch("ai_engine.orchestrator.run_builder")
@patch("ai_engine.orchestrator.wait_for_render_job")
@patch("ai_engine.orchestrator.run_single_review_round")
@patch("ai_engine.orchestrator.render_manim_scene")
def test_builder_loop_early_stop_on_success(
    mock_render_task: MagicMock,
    mock_review_round: MagicMock,
    mock_wait_job: MagicMock,
    mock_builder: MagicMock,
    mock_scene: Scene,
    mock_runtime_limits: RuntimeLimitsConfig,
) -> None:
    # Setup mocks
    store = MagicMock()
    store.get_scene.return_value = mock_scene
    job_store = MagicMock()
    llm = MagicMock()
    
    # Round 1: Builder returns code, Wait returns completed job, Review returns early_stop=True
    mock_builder.return_value = ("class GeneratedScene:\n    pass", "v1", {"duration_ms": 100})
    mock_wait_job.return_value = MagicMock(status="completed", asset_url="file:///tmp/x.mp4")
    mock_review_round.return_value = ReviewRoundResponse(
        static_parse_ok=True,
        static_imports_ok=True,
        code_review=ReviewResult(issues=[]),
        code_review_passed=True,
        visual_review_passed=True,
        early_stop=True,
        metrics={},
    )

    scene_out, report = run_builder_loop_phase(
        scene_id=mock_scene.id,
        store=store,
        job_store=job_store,
        llm=llm,
        yaml_data={},
        runtime_limits=mock_runtime_limits,
        preview_poll_timeout_seconds=10,
    )

    assert report["final_status"] == "completed"
    assert len(report["rounds"]) == 1
    assert mock_builder.call_count == 1
    assert mock_review_round.call_count == 1


@patch("ai_engine.orchestrator.run_builder")
@patch("ai_engine.orchestrator.wait_for_render_job")
@patch("ai_engine.orchestrator.run_single_review_round")
@patch("ai_engine.orchestrator.render_manim_scene")
def test_builder_loop_max_rounds_exceeded(
    mock_render_task: MagicMock,
    mock_review_round: MagicMock,
    mock_wait_job: MagicMock,
    mock_builder: MagicMock,
    mock_scene: Scene,
    mock_runtime_limits: RuntimeLimitsConfig,
) -> None:
    # Setup mocks
    store = MagicMock()
    store.get_scene.return_value = mock_scene
    job_store = MagicMock()
    llm = MagicMock()
    
    # Always fail review
    mock_builder.return_value = ("class GeneratedScene:\n    pass", "v1", {"duration_ms": 100})
    mock_wait_job.return_value = MagicMock(status="completed", asset_url="file:///tmp/x.mp4")
    mock_review_round.return_value = ReviewRoundResponse(
        static_parse_ok=True,
        static_imports_ok=True,
        code_review=ReviewResult(issues=[]),
        code_review_passed=False,
        visual_review_passed=False,
        early_stop=False,
        metrics={},
    )

    # Set max_rounds to 2 via yaml_data or extra_rounds param
    scene_out, report = run_builder_loop_phase(
        scene_id=mock_scene.id,
        store=store,
        job_store=job_store,
        llm=llm,
        yaml_data={"builder_review_loop": {"max_rounds": 2}},
        runtime_limits=mock_runtime_limits,
        preview_poll_timeout_seconds=10,
        extra_rounds=2,
    )

    assert report["final_status"] == "hitl_pending"
    assert len(report["rounds"]) == 2
    assert mock_builder.call_count == 2
    assert mock_review_round.call_count == 2
