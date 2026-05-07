from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
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
    planner_json = (
        Path(__file__).resolve().parents[2] / "fixtures" / "planner_output_valid.json"
    ).read_text(encoding="utf-8")
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient(planner_json=planner_json)
    app.dependency_overrides[get_content_store] = lambda: RedisContentStore(get_redis())
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _scene_with_code(client: TestClient) -> UUID:
    r0 = client.post("/v1/projects", json={"title": "R8", "source_language": "vi"})
    pid = UUID(r0.json()["id"])
    r1 = client.post(f"/v1/projects/{pid}/scenes", json={"scene_order": 0})
    sid = UUID(r1.json()["id"])
    assert client.post(f"/v1/scenes/{sid}/generate-storyboard", json={}).status_code == 200
    assert client.post(f"/v1/scenes/{sid}/approve-storyboard").status_code == 200
    assert client.post(f"/v1/scenes/{sid}/plan").status_code == 200
    rgc = client.post(f"/v1/scenes/{sid}/generate-code", json={"enqueue_preview": False})
    assert rgc.status_code == 200, rgc.text
    return sid


def test_review_round_endpoint_no_preview(api_client: TestClient) -> None:
    sid = _scene_with_code(api_client)
    r = api_client.post(f"/v1/scenes/{sid}/review-round", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code_review_passed"] is True
    assert body["visual_review_skipped_reason"] == "no_preview_video"
    assert body["early_stop"] is False
