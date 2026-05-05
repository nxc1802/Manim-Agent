from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from backend.api.deps import get_content_store, get_job_store, get_request_user_id
from backend.main import app
from fastapi.testclient import TestClient
from redis.exceptions import RedisError


@pytest.fixture
def client():
    return TestClient(app)


def test_enqueue_render_redis_error(client):
    pid = uuid4()
    sid = uuid4()
    uid = uuid4()

    mock_store = MagicMock()
    mock_store.create_queued_job.side_effect = RedisError("redis down")

    app.dependency_overrides[get_request_user_id] = lambda: uid
    app.dependency_overrides[get_content_store] = lambda: MagicMock()
    app.dependency_overrides[get_job_store] = lambda: mock_store

    with patch("backend.api.v1.render.project_readable_by_user"):
        res = client.post(
            f"/v1/projects/{pid}/render",
            json={"scene_id": str(sid), "render_type": "preview", "quality": "720p"},
        )
        assert res.status_code == 503
        assert res.json()["error"]["code"] == "redis_unavailable"

    app.dependency_overrides = {}


def test_enqueue_render_celery_error(client):
    pid = uuid4()
    sid = uuid4()
    uid = uuid4()

    app.dependency_overrides[get_request_user_id] = lambda: uid
    app.dependency_overrides[get_content_store] = lambda: MagicMock()
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
