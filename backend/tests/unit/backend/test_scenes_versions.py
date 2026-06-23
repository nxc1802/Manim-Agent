from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from backend.api.deps import get_content_store, get_job_store, get_request_user_id
from backend.main import app
from fastapi.testclient import TestClient
from shared.schemas.artifact_version import ArtifactVersion
from shared.schemas.scene import Scene


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def mock_store() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def mock_job_store() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def test_client(
    mock_store: MagicMock,
    mock_job_store: MagicMock,
) -> TestClient:
    user_id = UUID("00000000-0000-0000-0000-000000000000")
    app.dependency_overrides[get_content_store] = lambda: mock_store
    app.dependency_overrides[get_job_store] = lambda: mock_job_store
    app.dependency_overrides[get_request_user_id] = lambda: user_id

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def test_get_scene_versions(test_client: TestClient, mock_store: MagicMock) -> None:
    scene_id = uuid4()
    project_id = uuid4()
    user_id = UUID("00000000-0000-0000-0000-000000000000")  # default test client user_id

    mock_store.get_scene.return_value = Scene(
        id=scene_id,
        project_id=project_id,
        scene_order=0,
        storyboard_status="approved",
    )
    mock_store.get_project.return_value = MagicMock(
        id=project_id,
        user_id=user_id,
        title="Test Project",
    )

    # Mock list_artifact_versions
    ver1 = ArtifactVersion(
        id=uuid4(),
        entity_type="dsl",
        entity_id=scene_id,
        version=1,
        content_hash="abc",
        content={"beats": []},
        created_by="user_edit",
    )
    mock_store.list_artifact_versions.return_value = [ver1]

    # Verify endpoint returns versions
    response = test_client.get(f"/v1/scenes/{scene_id}/versions?entity_type=dsl")
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data) == 1
    assert data[0]["version"] == 1
    assert data[0]["entity_type"] == "dsl"


def test_get_scene_versions_rejects_unknown_entity_type(
    test_client: TestClient,
    mock_store: MagicMock,
) -> None:
    scene_id = uuid4()

    response = test_client.get(f"/v1/scenes/{scene_id}/versions?entity_type=bogus")

    assert response.status_code == 422
    mock_store.get_scene.assert_not_called()


def test_rollback_scene_artifact(test_client: TestClient, mock_store: MagicMock) -> None:
    scene_id = uuid4()
    project_id = uuid4()
    user_id = UUID("00000000-0000-0000-0000-000000000000")

    mock_scene = Scene(
        id=scene_id,
        project_id=project_id,
        scene_order=0,
        storyboard_status="approved",
    )
    mock_store.get_scene.return_value = mock_scene
    mock_store.get_project.return_value = MagicMock(
        id=project_id,
        user_id=user_id,
        title="Test Project",
    )

    # Mock target version to roll back to
    target_ver = ArtifactVersion(
        id=uuid4(),
        entity_type="dsl",
        entity_id=scene_id,
        version=1,
        content_hash="abc",
        content={"beats": []},
        created_by="user_edit",
    )
    mock_store.get_artifact_version.return_value = target_ver

    # Mock history list for version numbering
    mock_store.list_artifact_versions.return_value = [target_ver]

    response = test_client.post(
        f"/v1/scenes/{scene_id}/rollback",
        json={"entity_type": "dsl", "target_version": 1},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["entity_type"] == "dsl"
    assert data["version"] == 2
    assert data["parent_version"] == 1

    # Verify update_scene was called on DB
    mock_store.update_scene.assert_any_call(
        scene_id,
        scene_dsl={"beats": []},
        scene_dsl_version=2,
    )


@patch("backend.api.v1.scenes_versions.render_manim_scene")
def test_edit_scene_dsl_directly(
    mock_render_task: MagicMock,
    test_client: TestClient,
    mock_store: MagicMock,
    mock_job_store: MagicMock,
) -> None:
    scene_id = uuid4()
    project_id = uuid4()
    user_id = UUID("00000000-0000-0000-0000-000000000000")

    mock_scene = Scene(
        id=scene_id,
        project_id=project_id,
        scene_order=0,
        storyboard_status="approved",
    )
    mock_store.get_scene.return_value = mock_scene
    mock_store.get_project.return_value = MagicMock(
        id=project_id,
        user_id=user_id,
        title="Test Project",
    )
    mock_store.update_scene.return_value = mock_scene
    mock_store.list_artifact_versions.return_value = []

    dsl_code = """
from shared.schemas.scene_dsl import (
    AnimationStep, Position, SceneDSLBeat, ThemeConfig, VisualElement
)

class GeneratedSceneDSL:
    title = "Direct DSL Edit Title"
    global_theme = ThemeConfig(primary_color="BLUE")
    beats = [
        SceneDSLBeat(
            id="beat_1",
            label="Intro Beat",
            duration_seconds=2.0,
            visual_elements=[],
            animations=[]
        )
    ]
"""
    response = test_client.patch(
        f"/v1/scenes/{scene_id}/dsl",
        json={"dsl_code": dsl_code},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "preview_job_id" in data
    assert mock_render_task.apply_async.called
