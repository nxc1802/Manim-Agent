"""Release-gate E2E: Director → Planner → Builder with a live LLM (no FakeLLMClient override)."""

from __future__ import annotations

from uuid import UUID

import pytest
from backend.main import app
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.e2e_llm, pytest.mark.usefixtures("e2e_llm_gate")]


def _bootstrap_scene_with_storyboard(client: TestClient) -> UUID:
    """Create project + scene; seed a short English storyboard (minimal tokens)."""
    r0 = client.post(
        "/v1/projects",
        json={
            "title": "E2E LLM gate",
            "description": "Automated release check",
            "source_language": "en",
        },
    )
    assert r0.status_code == 201, r0.text
    project_id = UUID(r0.json()["id"])
    r1 = client.post(
        f"/v1/projects/{project_id}/scenes",
        json={
            "scene_order": 0,
            "storyboard_text": (
                "## Scene\nOne equation: E = mc^2. Narrator explains energy–mass "
                "equivalence in two short sentences."
            ),
        },
    )
    assert r1.status_code == 201, r1.text
    return UUID(r1.json()["id"])


@pytest.mark.timeout(900)
def test_storyboard_approve_plan_generate_code_live_llm() -> None:
    """Full text pipeline with real provider (LiteLLM). Uses FakeRedis from root conftest.

    Model routing comes from ``AGENT_MODELS_YAML`` when set; otherwise the bundled
    ``ai_engine/config/agent_models.example.yaml`` (see ``backend.api.deps``).
    """
    with TestClient(app) as client:
        scene_id = _bootstrap_scene_with_storyboard(client)
        assert client.post(f"/v1/scenes/{scene_id}/approve-storyboard").status_code == 200
        r_plan = client.post(f"/v1/scenes/{scene_id}/plan")
        assert r_plan.status_code == 200, r_plan.text
        scene_after = r_plan.json()
        assert scene_after.get("planner_output") is not None

        r_code = client.post(
            f"/v1/scenes/{scene_id}/generate-code",
            json={"enqueue_preview": False},
        )
        assert r_code.status_code == 200, r_code.text
        body = r_code.json()
        code = body["scene"]["manim_code"]
        assert isinstance(code, str) and len(code) > 80
        assert "GeneratedScene" in code
        assert "from manim" in code.lower() or "import" in code
