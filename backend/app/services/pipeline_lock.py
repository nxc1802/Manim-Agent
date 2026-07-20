from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from fastapi import HTTPException, status
from redis.exceptions import LockError, RedisError

from app.core.config import settings
from app.services.redis_client import get_redis

logger = logging.getLogger(__name__)


@contextmanager
def pipeline_target_lock(project_id: UUID, scene_id: UUID | None) -> Iterator[None]:
    """Serialize mutations for one durable Master or Builder target.

    Supabase remains authoritative for runs and steps, while this short-lived
    Redis lock closes the cross-table window between replacing a run and
    applying its output to the project/scene artifact.
    """

    target = str(scene_id) if scene_id is not None else "project"
    key = f"{settings.redis_prefix}:lock:hitl:{project_id}:{target}"
    lock = get_redis().lock(
        key,
        timeout=settings.pipeline_lock_timeout_seconds,
        blocking_timeout=settings.pipeline_lock_blocking_seconds,
    )
    try:
        acquired = bool(lock.acquire())
    except RedisError as exc:
        logger.exception(
            "Pipeline lock unavailable project_id=%s scene_id=%s",
            project_id,
            scene_id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pipeline coordination is temporarily unavailable",
        ) from exc
    if not acquired:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another pipeline operation is still updating this target",
        )
    try:
        yield
    finally:
        try:
            lock.release()
        except LockError:
            # The mutation has already completed. Log loss of ownership because
            # it indicates that an operation exceeded the configured safety TTL.
            logger.exception(
                "Pipeline lock ownership lost project_id=%s scene_id=%s",
                project_id,
                scene_id,
            )
