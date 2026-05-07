from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from ai_engine.builder_loop import run_builder_loop_phase, run_single_review_round_ex
from ai_engine.config import BuilderReviewLoopConfig, RuntimeLimitsConfig
from ai_engine.llm_client import FakeLLMClient
from shared.constants import ReviewLoopMode, SeverityLevel


@pytest.fixture
def rt() -> RuntimeLimitsConfig:
    return RuntimeLimitsConfig(
        worker_man_render_timeout_seconds=3600,
        worker_tts_subprocess_timeout_seconds=900,
        preview_poll_timeout_seconds=900,
        preview_poll_interval_seconds=0.5,
        llm_timeout_default_seconds=600,
        llm_timeouts={},
    )


@pytest.mark.anyio
async def test_run_single_review_round_ex_visual_error(rt: RuntimeLimitsConfig) -> None:
    llm = FakeLLMClient()
    review_cfg = BuilderReviewLoopConfig(
        max_rounds=3,
        early_stop_require_all=("code_review_passed", "visual_review_passed"),
        code_agent_blocking_issues_empty=True,
        code_static_ast_parse_ok=True,
        code_static_forbidden_imports_ok=True,
        visual_agent_blocking_issues_empty=True,
        visual_reviewer_enabled=True,
        blocking_severity_min=SeverityLevel.ERROR,
        stop_when_only_info_severity=False,
        on_max_rounds_exceeded="hitl_or_fail",
    )

    with patch("ai_engine.builder_loop.extract_frame_at_timestamp") as mock_extract:
        mock_extract.side_effect = Exception("vision error")

        resp, prompts = await run_single_review_round_ex(
            llm=llm,
            review_cfg=review_cfg,
            code_llm=MagicMock(),
            visual_llm=MagicMock(),
            manim_code="class S(Scene): ...",
            sandbox_limits=MagicMock(),
            preview_video_path="fake.mp4",
            extract_preview_frame=mock_extract,
            runtime_limits=rt,
        )
        assert resp.visual_review_skipped_reason == "visual_review_error"
        assert resp.visual_review_passed is False


@pytest.mark.anyio
async def test_run_builder_loop_phase_max_rounds(rt: RuntimeLimitsConfig) -> None:
    store = MagicMock()
    job_store = MagicMock()
    llm = FakeLLMClient()

    sid = uuid4()
    pid = uuid4()
    mock_scene = MagicMock()
    mock_scene.id = sid
    mock_scene.project_id = pid
    mock_scene.planner_output = {
        "version": "1",
        "beats": [{"step_label": "intro", "narration_hint": "Hi", "primitives": []}],
    }
    mock_scene.sync_segments = None
    mock_scene.manim_code_version = 1
    store.get_scene.return_value = mock_scene
    store.update_scene.return_value = mock_scene

    yaml_data = {"builder_review_loop": {"max_rounds": 1, "on_max_rounds_exceeded": "hitl_or_fail"}}

    with (
        patch("ai_engine.builder_loop.wait_for_render_job") as mock_wait,
        patch("ai_engine.builder_loop.insert_pipeline_run_row"),
        patch("ai_engine.builder_loop.insert_agent_log_row"),
        patch("ai_engine.builder_loop.save_agent_interaction"),
    ):
        mock_wait.return_value = MagicMock(status="failed", logs="error")

        scene, report = await run_builder_loop_phase(
            scene_id=sid,
            store=store,
            job_store=job_store,
            llm=llm,
            yaml_data=yaml_data,
            runtime_limits=rt,
            preview_poll_timeout_seconds=10,
            mode=ReviewLoopMode.AUTO,
        )
        assert report["final_status"] == "failed"
        assert len(report["rounds"]) == 1
