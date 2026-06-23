from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from backend.api.deps import get_content_store, get_job_store, get_request_user_id
from backend.main import app
from fastapi.testclient import TestClient
from redis.exceptions import RedisError


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_enqueue_render_redis_error(client: TestClient) -> None:
    pid = uuid4()
    sid = uuid4()
    uid = uuid4()

    mock_store = MagicMock()
    mock_store.create_queued_job.side_effect = RedisError("redis down")

    app.dependency_overrides[get_request_user_id] = lambda: uid
    content_store = MagicMock()
    content_store.get_scene.return_value = MagicMock(
        project_id=pid,
        manim_code=(
            "from manim import *\n"
            "class GeneratedScene(Scene):\n"
            "    def construct(self):\n"
            "        pass\n"
        ),
    )
    app.dependency_overrides[get_content_store] = lambda: content_store
    app.dependency_overrides[get_job_store] = lambda: mock_store

    with patch("backend.api.v1.render.project_readable_by_user"):
        res = client.post(
            f"/v1/projects/{pid}/render",
            json={"scene_id": str(sid), "render_type": "preview", "quality": "720p"},
        )
        assert res.status_code == 503
        assert res.json()["error"]["code"] == "redis_unavailable"

    app.dependency_overrides = {}


def test_enqueue_render_celery_error(client: TestClient) -> None:
    pid = uuid4()
    sid = uuid4()
    uid = uuid4()

    app.dependency_overrides[get_request_user_id] = lambda: uid
    content_store = MagicMock()
    content_store.get_scene.return_value = MagicMock(
        project_id=pid,
        manim_code=(
            "from manim import *\n"
            "class GeneratedScene(Scene):\n"
            "    def construct(self):\n"
            "        pass\n"
        ),
    )
    app.dependency_overrides[get_content_store] = lambda: content_store
    app.dependency_overrides[get_job_store] = lambda: MagicMock()

    with (
        patch("backend.api.v1.render.project_readable_by_user"),
        patch("backend.api.v1.render.render_manim_scene.apply_async") as mock_celery,
    ):
        mock_celery.side_effect = Exception("celery down")

        res = client.post(
            f"/v1/projects/{pid}/render",
            json={"scene_id": str(sid), "render_type": "preview", "quality": "720p"},
        )
        assert res.status_code == 503
        assert res.json()["error"]["code"] == "broker_unavailable"

    app.dependency_overrides = {}


def test_enqueue_render_rejects_scene_from_another_project(client: TestClient) -> None:
    project_id = uuid4()
    content_store = MagicMock()
    content_store.get_scene.return_value = MagicMock(project_id=uuid4())
    job_store = MagicMock()

    app.dependency_overrides[get_request_user_id] = lambda: uuid4()
    app.dependency_overrides[get_content_store] = lambda: content_store
    app.dependency_overrides[get_job_store] = lambda: job_store

    with patch("backend.api.v1.render.project_readable_by_user"):
        response = client.post(
            f"/v1/projects/{project_id}/render",
            json={"scene_id": str(uuid4()), "render_type": "preview", "quality": "720p"},
        )

    assert response.status_code == 404
    job_store.create_queued_job.assert_not_called()
    app.dependency_overrides = {}
