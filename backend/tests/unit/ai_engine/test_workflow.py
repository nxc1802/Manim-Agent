from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from ai_engine.workflow import run_project_workflow
from shared.constants import ReviewLoopMode


@pytest.mark.asyncio
async def test_run_project_workflow_success() -> None:
    project_id = uuid4()
    user_id = uuid4()
    scene_id1 = uuid4()
    scene_id2 = uuid4()

    # Mock content store
    mock_store = MagicMock()
    mock_scene1 = MagicMock(
        id=scene_id1,
        project_id=project_id,
        storyboard_status="approved",
        storyboard_text="Scene 1 text",
        planner_output={"beats": []},
        timestamps={"segments": []},
        sync_segments={"intro": 1.0},
        review_loop_status="completed",
        manim_code="class Scene1: pass",
        voice_script_status="approved",
        plan_status="approved",
    )
    mock_scene2 = MagicMock(
        id=scene_id2,
        project_id=project_id,
        storyboard_status="approved",
        storyboard_text="Scene 2 text",
        planner_output={"beats": []},
        timestamps={"segments": []},
        sync_segments={"intro": 2.0},
        review_loop_status="completed",
        manim_code="class Scene2: pass",
        voice_script_status="approved",
        plan_status="approved",
    )

    def get_scene(sid: object) -> MagicMock | None:
        if sid == scene_id1:
            return mock_scene1
        if sid == scene_id2:
            return mock_scene2
        return None

    mock_store.get_scene.side_effect = get_scene

    # Mock voice job store
    mock_vstore = MagicMock()
    mock_job = MagicMock(status="completed", error=None)
    mock_vstore.get.return_value = mock_job

    # Mock render job store
    mock_job_store = MagicMock()

    # Mock llm
    mock_llm = MagicMock()

    # Mock yaml data and runtime limits
    yaml_data: dict[str, object] = {}
    mock_rt = MagicMock()
    mock_rt.preview_poll_timeout_seconds = 10.0

    # Run workflow
    with (
        patch("backend.services.scene_service.synthesize_voice"),
        patch("backend.services.scene_service.insert_voice_job_row"),
    ):
        state = await run_project_workflow(
            project_id=project_id,
            user_id=user_id,
            scene_ids=[scene_id1, scene_id2],
            store=mock_store,
            vstore=mock_vstore,
            job_store=mock_job_store,
            llm=mock_llm,
            yaml_data=yaml_data,
            runtime_limits=mock_rt,
            mode=ReviewLoopMode.AUTO,
        )

    assert not state["errors"]
    assert state["plan_status"][str(scene_id1)] == "approved"
    assert state["plan_status"][str(scene_id2)] == "approved"
    assert state["sync_status"][str(scene_id1)] == "synced"
    assert state["sync_status"][str(scene_id2)] == "synced"
    assert state["builder_loop_status"][str(scene_id1)] == "completed"
    assert state["builder_loop_status"][str(scene_id2)] == "completed"
