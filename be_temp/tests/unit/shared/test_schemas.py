from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from shared.schemas.project import Project, ProjectCreate
from shared.schemas.render_job import RenderJob
from shared.schemas.scene import Scene


def test_project_create_round_trip() -> None:
    payload = {
        "title": "Binary Search",
        "description": "Explain algorithm",
        "source_language": "vi",
    }
    model = ProjectCreate.model_validate(payload)
    dumped = model.model_dump(mode="json")
    again = ProjectCreate.model_validate(dumped)
    assert again == model


def test_project_round_trip_json_mode() -> None:
    now = datetime.now(tz=UTC)
    project_id = uuid4()
    user_id = uuid4()
    payload = {
        "id": str(project_id),
        "user_id": str(user_id),
        "title": "Title",
        "description": None,
        "source_language": "vi",
        "config": {"theme": "dark"},
        "status": "draft",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    model = Project.model_validate(payload)
    dumped = model.model_dump(mode="json")
    again = Project.model_validate(dumped)
    assert again == model


def test_scene_round_trip_json_mode() -> None:
    now = datetime.now(tz=UTC)
    scene_id = uuid4()
    project_id = uuid4()
    payload = {
        "id": str(scene_id),
        "project_id": str(project_id),
        "scene_order": 0,
        "storyboard_status": "pending_review",
        "storyboard_text": "Intro",
        "voice_script": None,
        "planner_output": None,
        "sync_segments": None,
        "manim_code": None,
        "manim_code_version": 1,
        "audio_url": None,
        "timestamps": [{"word": "hi", "start": 0.0, "end": 0.2}],
        "duration_seconds": "12.500",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    model = Scene.model_validate(payload)
    dumped = model.model_dump(mode="json")
    again = Scene.model_validate(dumped)
    assert again == model
    assert again.duration_seconds == Decimal("12.500")


def test_render_job_round_trip_json_mode() -> None:
    now = datetime.now(tz=UTC)
    job_id = uuid4()
    project_id = uuid4()
    payload = {
        "id": str(job_id),
        "project_id": str(project_id),
        "scene_id": None,
        "job_type": "preview",
        "render_quality": None,
        "status": "queued",
        "progress": 0,
        "logs": None,
        "asset_url": None,
        "error_code": None,
        "webhook_url": None,
        "docker_image_tag": None,
        "created_at": now.isoformat(),
        "started_at": None,
        "completed_at": None,
    }
    model = RenderJob.model_validate(payload)
    dumped = model.model_dump(mode="json")
    again = RenderJob.model_validate(dumped)
    assert again == model
