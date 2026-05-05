from __future__ import annotations

from pathlib import Path
from typing import Generator
from uuid import UUID

import pytest
from ai_engine.llm_client import FakeLLMClient
from backend.api.deps import get_llm_client
from backend.main import app
from backend.services.redis_client import configure_redis
from fakeredis import FakeRedis
from fastapi.testclient import TestClient


@pytest.fixture()
def api_client() -> Generator[TestClient, None, None]:
    from backend.api.deps import get_content_store
    from backend.db.content_store import RedisContentStore
    from backend.services.redis_client import get_redis

    configure_redis(FakeRedis(decode_responses=True))
    fixture_json = Path(__file__).resolve().parents[2] / "fixtures" / "planner_output_valid.json"
    planner_json = fixture_json.read_text(encoding="utf-8")
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient(planner_json=planner_json)
    app.dependency_overrides[get_content_store] = lambda: RedisContentStore(get_redis())
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_director_hitl_planner_flow(api_client: TestClient) -> None:
    r0 = api_client.post(
        "/v1/projects",
        json={
            "title": "Demo",
            "description": "Explain X",
            "source_language": "vi",
        },
    )
    assert r0.status_code == 201
    project_id = UUID(r0.json()["id"])

    r1 = api_client.post(
        f"/v1/projects/{project_id}/scenes",
        json={"scene_order": 0},
    )
    assert r1.status_code == 201
    scene_id = UUID(r1.json()["id"])
    assert r1.json()["storyboard_status"] == "missing"

    r2 = api_client.post(f"/v1/scenes/{scene_id}/generate-storyboard", json={})
    assert r2.status_code == 200
    body = r2.json()
    assert body["storyboard_status"] == "pending_review"
    assert body["storyboard_text"]
    assert "# Storyboard" in body["storyboard_text"]

    r_bad = api_client.post(f"/v1/scenes/{scene_id}/plan")
    assert r_bad.status_code == 400

    r3 = api_client.post(f"/v1/scenes/{scene_id}/approve-storyboard")
    assert r3.status_code == 200
    assert r3.json()["storyboard_status"] == "approved"

    r4 = api_client.post(f"/v1/scenes/{scene_id}/plan")
    assert r4.status_code == 200
    plan = r4.json()["planner_output"]
    assert isinstance(plan, dict)
    assert plan["version"] == "1"
    assert len(plan["beats"]) >= 1


def test_project_level_storyboard_approval(api_client: TestClient) -> None:
    r0 = api_client.post("/v1/projects", json={"title": "P2", "source_language": "vi"})
    project_id = UUID(r0.json()["id"])
    s1 = api_client.post(f"/v1/projects/{project_id}/scenes", json={"scene_order": 0})
    s2 = api_client.post(f"/v1/projects/{project_id}/scenes", json={"scene_order": 1})
    id1 = UUID(s1.json()["id"])
    id2 = UUID(s2.json()["id"])
    assert api_client.post(f"/v1/scenes/{id1}/generate-storyboard", json={}).status_code == 200
    assert api_client.post(f"/v1/scenes/{id2}/generate-storyboard", json={}).status_code == 200

    r_approve = api_client.post(f"/v1/projects/{project_id}/approve-storyboard")
    assert r_approve.status_code == 200
    scenes = r_approve.json()
    assert len(scenes) == 2
    assert {s["storyboard_status"] for s in scenes} == {"approved"}


def test_hitl_approve_requires_pending_review(api_client: TestClient) -> None:
    r0 = api_client.post("/v1/projects", json={"title": "P3", "source_language": "vi"})
    project_id = UUID(r0.json()["id"])
    s = api_client.post(f"/v1/projects/{project_id}/scenes", json={"scene_order": 0})
    scene_id = UUID(s.json()["id"])
    r_conflict = api_client.post(f"/v1/scenes/{scene_id}/approve-storyboard")
    assert r_conflict.status_code == 409
