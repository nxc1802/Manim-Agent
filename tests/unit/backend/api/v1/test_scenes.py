from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from backend.api.deps import get_content_store, get_request_user_id
from backend.main import app
from fastapi.testclient import TestClient
from shared.schemas.scene import Scene

client = TestClient(app)


@pytest.fixture
def mock_store():
    store = MagicMock()
    app.dependency_overrides[get_content_store] = lambda: store
    yield store
    app.dependency_overrides.pop(get_content_store, None)


@pytest.fixture
def mock_user():
    uid = uuid4()
    app.dependency_overrides[get_request_user_id] = lambda: uid
    yield uid
    app.dependency_overrides.pop(get_request_user_id, None)


def test_get_scene_not_found(mock_store, mock_user):
    mock_store.get_scene.return_value = None
    resp = client.get(f"/v1/scenes/{uuid4()}")
    assert resp.status_code == 404





def test_get_scene_success(mock_store, mock_user):
    sid = uuid4()
    pid = uuid4()
    now = datetime.now(tz=UTC)
    mock_scene = Scene(id=sid, project_id=pid, scene_order=1, created_at=now, updated_at=now)
    mock_store.get_scene.return_value = mock_scene
    mock_store.get_project.return_value = MagicMock(id=pid, user_id=mock_user)

    resp = client.get(f"/v1/scenes/{sid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == str(sid)


@pytest.mark.anyio
async def test_generate_storyboard_success(mock_store, mock_user):
    sid = uuid4()
    pid = uuid4()
    now = datetime.now(tz=UTC)
    mock_scene = Scene(
        id=sid,
        project_id=pid,
        scene_order=1,
        created_at=now,
        updated_at=now,
        storyboard_status="missing",
    )
    mock_store.get_scene.return_value = mock_scene
    mock_store.get_project.return_value = MagicMock(
        id=pid, user_id=mock_user, title="T", description="D", target_scenes=None
    )

    with patch("backend.api.v1.scenes.run_storyboard_phase") as mock_run:
        mock_run.return_value = ("story text", "v1", {"duration_ms": 1}, "sys", "usr")
        mock_store.update_scene.return_value = mock_scene

        resp = client.post(f"/v1/scenes/{sid}/generate-storyboard")
        assert resp.status_code == 200


def test_approve_storyboard_fail(mock_store, mock_user):
    sid = uuid4()
    pid = uuid4()
    now = datetime.now(tz=UTC)
    mock_scene = Scene(
        id=sid,
        project_id=pid,
        scene_order=1,
        created_at=now,
        updated_at=now,
        storyboard_status="missing",
    )
    mock_store.get_scene.return_value = mock_scene
    mock_store.get_project.return_value = MagicMock(id=pid, user_id=mock_user)

    resp = client.post(f"/v1/scenes/{sid}/approve-storyboard")
    assert resp.status_code == 409
