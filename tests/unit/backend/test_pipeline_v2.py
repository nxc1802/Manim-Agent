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
from worker.runtime import execute_render_job


@pytest.fixture()
def api_client() -> TestClient:
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


def _bootstrap_planned_scene(client: TestClient) -> tuple[UUID, UUID]:
    r0 = client.post(
        "/v1/projects",
        json={"title": "Phase5", "source_language": "vi"},
    )
    assert r0.status_code == 201, r0.text
    project_id = UUID(r0.json()["id"])
    r1 = client.post(f"/v1/projects/{project_id}/scenes", json={"scene_order": 0})
    assert r1.status_code == 201, r1.text
    scene_id = UUID(r1.json()["id"])
    assert client.post(f"/v1/scenes/{scene_id}/generate-storyboard", json={}).status_code == 200
    assert client.post(f"/v1/scenes/{scene_id}/approve-storyboard").status_code == 200
    assert client.post(f"/v1/scenes/{scene_id}/plan").status_code == 200
    return project_id, scene_id


def test_generate_code_requires_planner(api_client: TestClient) -> None:
    r0 = api_client.post("/v1/projects", json={"title": "X", "source_language": "vi"})
    project_id = UUID(r0.json()["id"])
    r1 = api_client.post(f"/v1/projects/{project_id}/scenes", json={"scene_order": 0})
    scene_id = UUID(r1.json()["id"])
    r2 = api_client.post(f"/v1/scenes/{scene_id}/generate-code", json={})
    assert r2.status_code == 400


def test_generate_code_persists_manim_code(api_client: TestClient) -> None:
    _project_id, scene_id = _bootstrap_planned_scene(api_client)
    r = api_client.post(f"/v1/scenes/{scene_id}/generate-code", json={"enqueue_preview": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["preview_job_id"] is None
    scene = body["scene"]
    assert scene["manim_code"]
    assert "GeneratedScene" in scene["manim_code"]
    assert scene["manim_code_version"] == 2


def test_generate_code_enqueue_preview_mocked_render(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _project_id, scene_id = _bootstrap_planned_scene(api_client)

    def fake_render(*, job_id: UUID, job_type: str, quality: str, **kwargs):  # noqa: ARG001
        from worker.renderer import RenderManimResult

        out = tmp_path / f"{job_id}.mp4"
        out.write_bytes(b"x")
        return RenderManimResult(out, out.parent, "", "", ["manim", "render"])

    monkeypatch.setattr("worker.runtime.render_manim_scene_to_disk", fake_render)

    def immediate(*args: object, **kwargs: object) -> None:
        a = kwargs.get("args", args[0] if args else ())
        assert isinstance(a, (list, tuple))
        execute_render_job(UUID(str(a[0])))

    monkeypatch.setattr("backend.api.v1.scenes.render_manim_scene.apply_async", immediate)

    r = api_client.post(f"/v1/scenes/{scene_id}/generate-code", json={"enqueue_preview": True})
    assert r.status_code == 200, r.text
    job_id = UUID(r.json()["preview_job_id"])
    detail = api_client.get(f"/v1/jobs/{job_id}")
    assert detail.status_code == 200, detail.text
    dj = detail.json()
    assert dj["status"] == "completed"
    assert dj["scene_id"] == str(scene_id)
