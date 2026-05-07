from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import fakeredis
from backend.services.job_store import RedisRenderJobStore


def test_job_store_roundtrip() -> None:
    r = fakeredis.FakeStrictRedis(decode_responses=True)
    store = RedisRenderJobStore(r)

    job_id = uuid4()
    project_id = uuid4()
    job = store.create_queued_job(
        job_id=job_id,
        project_id=project_id,
        scene_id=None,
        job_type="preview",
        render_quality="720p",
        webhook_url=None,
        docker_image_tag=None,
    )
    assert job.status == "queued"

    loaded = store.get(job_id)
    assert loaded is not None
    assert loaded.id == job_id

    updated = store.update(job_id, status="rendering", progress=50, logs="working")
    assert updated is not None
    assert updated.status == "rendering"
    loaded2 = store.get(job_id)
    assert loaded2 is not None
    assert loaded2.progress == 50


def test_job_store_update_model_copy_datetime() -> None:
    r = fakeredis.FakeStrictRedis(decode_responses=True)
    store = RedisRenderJobStore(r)
    job_id = uuid4()
    project_id = uuid4()
    store.create_queued_job(
        job_id=job_id,
        project_id=project_id,
        scene_id=None,
        job_type="full",
        render_quality="1080p",
        webhook_url=None,
        docker_image_tag="dev",
    )
    now = datetime.now(tz=UTC)
    store.update(job_id, started_at=now, status="rendering")
    loaded = store.get(job_id)
    assert loaded is not None
    assert loaded.started_at is not None
