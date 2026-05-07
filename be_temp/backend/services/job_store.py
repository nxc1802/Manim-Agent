from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from redis import Redis
from shared.schemas.render_job import RenderJob, RenderJobType, RenderQuality

from backend.core.config import settings


def _job_key(job_id: UUID) -> str:
    return f"{settings.redis_prefix}:render_job:{job_id}"


class RedisRenderJobStore:
    """Persist `RenderJob` JSON in Redis (shared by API and Celery worker)."""

    def __init__(self, client: Redis) -> None:
        self._r = client

    def get(self, job_id: UUID) -> RenderJob | None:
        raw = self._r.get(_job_key(job_id))
        if raw is None:
            return None
        data: dict[str, Any] = json.loads(cast(str, raw))
        return RenderJob.model_validate(data)

    def save(self, job: RenderJob) -> None:
        payload = job.model_dump(mode="json")
        self._r.set(_job_key(job.id), json.dumps(payload))

    def create_queued_job(
        self,
        *,
        job_id: UUID,
        project_id: UUID,
        scene_id: UUID | None,
        job_type: RenderJobType,
        render_quality: RenderQuality,
        webhook_url: str | None,
        docker_image_tag: str | None,
    ) -> RenderJob:
        now = datetime.now(tz=UTC)
        job = RenderJob(
            id=job_id,
            project_id=project_id,
            scene_id=scene_id,
            job_type=job_type,
            render_quality=render_quality,
            status="queued",
            progress=0,
            logs=None,
            asset_url=None,
            error_code=None,
            webhook_url=webhook_url,
            docker_image_tag=docker_image_tag,
            created_at=now,
            started_at=None,
            completed_at=None,
        )
        self.save(job)
        return job

    def update(self, job_id: UUID, **fields: object) -> RenderJob | None:
        job = self.get(job_id)
        if job is None:
            return None
        updated = job.model_copy(update=fields)
        self.save(updated)
        return updated

    def get_idempotent_job_id(self, key: str) -> UUID | None:
        raw = self._r.get(f"{settings.redis_prefix}:idempotency:{key}")
        if raw is None:
            return None
        return UUID(cast(str, raw))

    def set_idempotent_job_id(self, key: str, job_id: UUID, expiry: int = 86400) -> None:
        self._r.setex(
            f"{settings.redis_prefix}:idempotency:{key}",
            expiry,
            str(job_id),
        )
