from __future__ import annotations

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
def api_client() -> TestClient:
    from backend.api.deps import get_content_store
    from backend.db.content_store import RedisContentStore
    from backend.services.redis_client import get_redis

    configure_redis(FakeRedis(decode_responses=True))
    planner_json = (
        Path(__file__).resolve().parents[2] / "fixtures" / "planner_output_valid.json"
    ).read_text(encoding="utf-8")
    sync_json = (
        '{"version":"1","beats":[{"step_label":"intro","t_start":0,'
        '"t_end":1.0,"narration_window":"0-1","notes":"test"}]}'
    )
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient(
        planner_json=planner_json,
        sync_segments_json=sync_json,
    )
    app.dependency_overrides[get_content_store] = lambda: RedisContentStore(get_redis())
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_sync_timeline_endpoint(api_client: TestClient) -> None:
    r0 = api_client.post("/v1/projects", json={"title": "S8", "source_language": "vi"})
    pid = UUID(r0.json()["id"])
    r1 = api_client.post(f"/v1/projects/{pid}/scenes", json={"scene_order": 0})
    sid = UUID(r1.json()["id"])
    assert api_client.post(f"/v1/scenes/{sid}/generate-storyboard", json={}).status_code == 200
    assert api_client.post(f"/v1/scenes/{sid}/approve-storyboard").status_code == 200
    assert api_client.post(f"/v1/scenes/{sid}/plan").status_code == 200
    from backend.db.content_store import RedisContentStore
    from backend.services.redis_client import get_redis

    store = RedisContentStore(get_redis())
    store.update_scene(
        sid,
        timestamps={"version": "2", "granularity": "segment", "segments": []},
    )
    r2 = api_client.post(f"/v1/scenes/{sid}/sync-timeline")
    assert r2.status_code == 200, r2.text
    body = r2.json()
    sync = body["sync_segments"]
    assert sync["version"] == "1"
    labels = [b["step_label"] for b in sync["beats"]]
    assert "intro" in labels
    assert "explain" in labels
