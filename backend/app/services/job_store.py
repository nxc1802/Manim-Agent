from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from redis import Redis, WatchError
from shared.schemas.render_job import RenderJob, RenderJobType, RenderQuality

from app.core.config import settings
from app.services.cache import RedisJsonCache
from app.services.render_snapshot import job_source_fingerprint


def _job_key(job_id: UUID) -> str:
    return f"{settings.redis_prefix}:render_job:{job_id}"


def _project_jobs_key(project_id: UUID) -> str:
    return f"{settings.redis_prefix}:project_render_jobs:{project_id}"


def _job_index_version_key() -> str:
    return f"{settings.redis_prefix}:render_job_index_version"


def _active_job_key(
    project_id: UUID,
    scene_id: UUID | None,
    job_type: RenderJobType,
    render_quality: RenderQuality,
    source_fingerprint: str,
) -> str:
    scene_part = str(scene_id) if scene_id else "project"
    return (
        f"{settings.redis_prefix}:active_render_job:"
        f"v2:{project_id}:{scene_part}:{job_type}:{render_quality}:{source_fingerprint}"
    )


def _decode_job(raw: str) -> RenderJob:
    """Read the current schema while tolerating explicitly retired cache fields."""
    data: dict[str, Any] = json.loads(raw)
    # Render jobs are ephemeral Redis records and can outlive a deployment.
    # Keep this list explicit so genuine schema corruption still fails loudly.
    data.pop("webhook_url", None)
    return RenderJob.model_validate(data)


class RedisRenderJobStore:
    """Persist `RenderJob` JSON in Redis (shared by API and Celery worker)."""

    def __init__(self, client: Redis) -> None:
        self._r = client

    def get(self, job_id: UUID) -> RenderJob | None:
        raw = self._r.get(_job_key(job_id))
        if raw is None:
            return None
        return _decode_job(cast(str, raw))

    def save(self, job: RenderJob) -> None:
        payload = job.model_dump(mode="json")
        pipe = self._r.pipeline(transaction=True)
        pipe.set(_job_key(job.id), json.dumps(payload))
        pipe.sadd(_project_jobs_key(job.project_id), str(job.id))
        pipe.execute()
        RedisJsonCache(self._r).bump("dashboard:jobs")

    def create_queued_job(
        self,
        *,
        job_id: UUID,
        project_id: UUID,
        scene_id: UUID | None,
        job_type: RenderJobType,
        render_quality: RenderQuality,
        docker_image_tag: str | None,
        metadata: dict[str, Any] | None = None,
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
            docker_image_tag=docker_image_tag,
            metadata=metadata or {},
            created_at=now,
            started_at=None,
            completed_at=None,
        )
        self.save(job)
        return job

    def get_or_create_active_job(
        self,
        *,
        job_id: UUID,
        project_id: UUID,
        scene_id: UUID | None,
        job_type: RenderJobType,
        render_quality: RenderQuality,
        docker_image_tag: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[RenderJob, bool]:
        """Atomically reserve one active job per render target/configuration."""
        metadata = metadata or {}
        source_fingerprint = job_source_fingerprint(metadata)
        slot_key = _active_job_key(
            project_id,
            scene_id,
            job_type,
            render_quality,
            source_fingerprint,
        )
        for _attempt in range(5):
            try:
                with self._r.pipeline(transaction=True) as pipe:
                    pipe.watch(slot_key)
                    reserved_id = pipe.get(slot_key)
                    if reserved_id:
                        reserved = self.get(UUID(cast(str, reserved_id)))
                        if reserved is not None and reserved.status in {"queued", "rendering"}:
                            pipe.unwatch()
                            return reserved, False

                    # Backward-compatible discovery for active jobs created
                    # before slot reservations were introduced.
                    existing = self.find_active(
                        project_id=project_id,
                        scene_id=scene_id,
                        job_type=job_type,
                        render_quality=render_quality,
                        source_fingerprint=source_fingerprint,
                    )
                    if existing is not None:
                        pipe.multi()
                        pipe.set(slot_key, str(existing.id))
                        pipe.execute()
                        return existing, False

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
                        docker_image_tag=docker_image_tag,
                        metadata=metadata,
                        created_at=now,
                        started_at=None,
                        completed_at=None,
                    )
                    pipe.multi()
                    pipe.set(_job_key(job.id), json.dumps(job.model_dump(mode="json")))
                    pipe.sadd(_project_jobs_key(job.project_id), str(job.id))
                    pipe.set(slot_key, str(job.id))
                    pipe.execute()
                RedisJsonCache(self._r).bump("dashboard:jobs")
                return job, True
            except WatchError:
                continue
        raise RuntimeError("Unable to reserve an active render job")

    def update(self, job_id: UUID, **fields: object) -> RenderJob | None:
        job = self.get(job_id)
        if job is None:
            return None
        updated = job.model_copy(update=fields)
        self.save(updated)
        return updated

    def transition(
        self, job_id: UUID, *, expected_status: str, **fields: object
    ) -> RenderJob | None:
        """Atomically transition a job when its current status still matches."""
        key = _job_key(job_id)
        for _attempt in range(3):
            try:
                with self._r.pipeline(transaction=True) as pipe:
                    pipe.watch(key)
                    raw = pipe.get(key)
                    if raw is None:
                        pipe.unwatch()
                        return None
                    job = _decode_job(cast(str, raw))
                    if job.status != expected_status:
                        pipe.unwatch()
                        return None
                    slot_key = _active_job_key(
                        job.project_id,
                        job.scene_id,
                        job.job_type,
                        job.render_quality or "720p",
                        job_source_fingerprint(job.metadata),
                    )
                    pipe.watch(slot_key)
                    reserved_id = pipe.get(slot_key)
                    updated = job.model_copy(update=fields)
                    pipe.multi()
                    pipe.set(key, json.dumps(updated.model_dump(mode="json")))
                    pipe.sadd(_project_jobs_key(updated.project_id), str(updated.id))
                    if (
                        updated.status not in {"queued", "rendering"}
                        and reserved_id == str(updated.id)
                    ):
                        pipe.delete(slot_key)
                    pipe.execute()
                RedisJsonCache(self._r).bump("dashboard:jobs")
                return updated
            except WatchError:
                continue
        return None

    def list_for_project(self, project_id: UUID, *, active_only: bool = False) -> list[RenderJob]:
        self._ensure_project_indexes()
        job_ids = cast(set[str], self._r.smembers(_project_jobs_key(project_id)))
        if not job_ids:
            return []
        pipe = self._r.pipeline(transaction=False)
        for job_id in job_ids:
            pipe.get(_job_key(UUID(job_id)))
        jobs = [
            _decode_job(cast(str, raw))
            for raw in pipe.execute()
            if raw
        ]
        if active_only:
            jobs = [job for job in jobs if job.status in {"queued", "rendering"}]
        return sorted(jobs, key=lambda job: job.created_at, reverse=True)

    def find_active(
        self,
        *,
        project_id: UUID,
        scene_id: UUID | None,
        job_type: RenderJobType,
        render_quality: RenderQuality,
        source_fingerprint: str | None = None,
    ) -> RenderJob | None:
        return next(
            (
                job
                for job in self.list_for_project(project_id, active_only=True)
                if job.scene_id == scene_id
                and job.job_type == job_type
                and job.render_quality == render_quality
                and (
                    source_fingerprint is None
                    or job_source_fingerprint(job.metadata) == source_fingerprint
                )
            ),
            None,
        )

    def aggregate_for_projects(self, project_ids: set[UUID]) -> tuple[int, float]:
        """Return active-job count and completed render seconds from Redis."""
        if not project_ids:
            return 0, 0.0

        self._ensure_project_indexes()

        pipe = self._r.pipeline(transaction=False)
        for project_id in project_ids:
            pipe.smembers(_project_jobs_key(project_id))
        indexed_sets = pipe.execute()
        job_ids = {
            UUID(str(job_id))
            for indexed in indexed_sets
            for job_id in cast(set[str], indexed)
        }

        pipe = self._r.pipeline(transaction=False)
        for job_id in job_ids:
            pipe.get(_job_key(job_id))
        raw_jobs = pipe.execute()

        active_jobs = 0
        render_seconds = 0.0
        for raw in raw_jobs:
            if not raw:
                continue
            job = _decode_job(cast(str, raw))
            if job.project_id not in project_ids:
                continue
            if job.status in {"queued", "rendering"}:
                active_jobs += 1
            if job.status == "completed" and job.started_at and job.completed_at:
                render_seconds += max((job.completed_at - job.started_at).total_seconds(), 0)
        return active_jobs, render_seconds

    def _ensure_project_indexes(self) -> None:
        """One-time lazy backfill for jobs written before project indexes existed."""
        if self._r.get(_job_index_version_key()) == "1":
            return
        pipe = self._r.pipeline(transaction=False)
        for key in self._r.scan_iter(match=f"{settings.redis_prefix}:render_job:*"):
            raw = self._r.get(key)
            if not raw:
                continue
            job = _decode_job(cast(str, raw))
            pipe.sadd(_project_jobs_key(job.project_id), str(job.id))
            pipe.set(key, json.dumps(job.model_dump(mode="json")))
        pipe.set(_job_index_version_key(), "1")
        pipe.execute()

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
