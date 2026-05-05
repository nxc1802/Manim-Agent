from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import fakeredis
import pytest
from backend.core.config import settings
from backend.db.content_store import RedisContentStore
from backend.main import app
from backend.services.redis_client import configure_redis
from fastapi.testclient import TestClient
from worker.runtime import execute_render_job


@pytest.fixture()
def fake_redis() -> fakeredis.FakeStrictRedis:
    r = fakeredis.FakeStrictRedis(decode_responses=True)
    configure_redis(r)
    return r


def test_enqueue_then_execute_mocked_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_redis: fakeredis.FakeStrictRedis,
) -> None:
    assert fake_redis.ping() is True

    def fake_render(*, job_id: UUID, job_type: str, quality: str, **kwargs):  # noqa: ARG001
        from worker.renderer import RenderManimResult

        out = tmp_path / f"{job_id}.mp4"
        out.write_bytes(b"not-really-mp4")
        return RenderManimResult(out, out.parent, "", "", ["manim", "render"])

    monkeypatch.setattr("worker.runtime.render_manim_scene_to_disk", fake_render)

    def immediate(*args: object, **kwargs: object) -> None:
        a = kwargs.get("args", args[0] if args else ())
        assert isinstance(a, (list, tuple))
        execute_render_job(UUID(str(a[0])))

    monkeypatch.setattr("backend.api.v1.render.render_manim_scene.apply_async", immediate)

    store = RedisContentStore(fake_redis)
    project_id = uuid4()
    store.create_project(
        project_id=project_id,
        user_id=settings.dev_default_user_id,
        title="Render test",
        description=None,
        source_language="vi",
        status="draft",
    )

    client = TestClient(app)
    resp = client.post(
        f"/v1/projects/{project_id}/render",
        json={"render_type": "preview", "quality": "720p"},
    )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]

    detail = client.get(f"/v1/jobs/{job_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["status"] == "completed"
    assert body["asset_url"].startswith("file://")
    assert body["render_quality"] == "720p"
