from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from redis import Redis
from shared.schemas.voice_job import VoiceJob


def _voice_job_key(job_id: UUID) -> str:
    return f"manim_agent:voice_job:{job_id}"


class RedisVoiceJobStore:
    """Persist `VoiceJob` JSON in Redis (shared by API and TTS Celery worker)."""

    def __init__(self, client: Redis) -> None:
        self._r = client

    def get(self, job_id: UUID) -> VoiceJob | None:
        raw = self._r.get(_voice_job_key(job_id))
        if raw is None:
            return None
        data: dict[str, Any] = json.loads(cast(str, raw))
        return VoiceJob.model_validate(data)

    def save(self, job: VoiceJob) -> None:
        payload = job.model_dump(mode="json")
        self._r.set(_voice_job_key(job.id), json.dumps(payload))

    def create_queued_job(
        self,
        *,
        job_id: UUID,
        project_id: UUID,
        scene_id: UUID,
        metadata: dict[str, Any],
        voice_engine: str = "piper",
        docker_image_tag: str | None = None,
    ) -> VoiceJob:
        now = datetime.now(tz=UTC)
        job = VoiceJob(
            id=job_id,
            project_id=project_id,
            scene_id=scene_id,
            status="queued",
            progress=0,
            logs=None,
            asset_url=None,
            error_code=None,
            metadata=metadata,
            voice_engine=voice_engine,
            docker_image_tag=docker_image_tag,
            created_at=now,
            started_at=None,
            completed_at=None,
        )
        self.save(job)
        return job

    def update(self, job_id: UUID, **fields: object) -> VoiceJob | None:
        job = self.get(job_id)
        if job is None:
            return None
        updated = job.model_copy(update=fields)
        self.save(updated)
        return updated
