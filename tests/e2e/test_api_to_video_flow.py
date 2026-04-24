from __future__ import annotations

from pathlib import Path
from uuid import UUID
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


def test_api_to_video_flow_mocked(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Full flow mock: Create -> Storyboard -> Approve -> Plan -> Voice -> Render."""
    
    # Mock LLM and Worker tasks to avoid network/IO
    from ai_engine.llm_client import FakeLLMClient
    
    # 1. Create Project
    resp = api_client.post("/v1/projects", json={
        "title": "E2E Demo",
        "source_language": "vi"
    })
    assert resp.status_code == 201
    project_id = resp.json()["id"]
    
    # 2. Add Scene
    resp = api_client.post(f"/v1/projects/{project_id}/scenes", json={
        "scene_order": 0
    })
    assert resp.status_code == 201
    scene_id = resp.json()["id"]
    
    # 3. Generate Storyboard
    resp = api_client.post(f"/v1/scenes/{scene_id}/generate-storyboard", json={})
    assert resp.status_code == 200
    
    # 4. Approve Storyboard
    resp = api_client.post(f"/v1/scenes/{scene_id}/approve-storyboard")
    assert resp.status_code == 200
    
    # 5. Plan
    resp = api_client.post(f"/v1/scenes/{scene_id}/plan")
    assert resp.status_code == 200
    
    # 6. Enqueue Voice
    # Mock synthesize_voice task
    with patch("backend.api.v1.scenes.synthesize_voice") as mock_voice_task:
        resp = api_client.post(f"/v1/scenes/{scene_id}/voice", json={})
        assert resp.status_code == 202
        voice_job_id = resp.json()["voice_job_id"]
        assert mock_voice_task.apply_async.called
    
    # 7. Start Render Review Loop
    # Mock orchestrator to skip actual loop and return completed
    with patch("backend.api.v1.scenes.run_builder_loop_phase") as mock_loop:
        from shared.schemas.scene import Scene
        # Create a mock Scene instance that behaves like a Pydantic model
        m_scene = MagicMock(spec=Scene)
        m_scene.id = UUID(scene_id)
        m_scene.review_loop_status = "completed"
        
        mock_loop.return_value = (m_scene, {"final_status": "completed"})
        
        resp = api_client.post(f"/v1/scenes/{scene_id}/builder-review-loop", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["report"]["final_status"] == "completed"
        assert body["review_loop_status"] == "completed"
