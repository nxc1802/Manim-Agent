from __future__ import annotations

from uuid import UUID

from celery import Celery
from kombu.exceptions import OperationalError as KombuOperationalError
from redis.exceptions import RedisError

from app.core.config import settings


class AiQueueUnavailable(RuntimeError):
    """The task broker did not accept a dispatch request."""


class AiQueue:
    """Thin task producer. Backend never imports or executes AI Core code."""

    def __init__(self, celery_app: Celery | None = None) -> None:
        self._celery = celery_app or Celery(
            "manim_backend", broker=settings.celery_broker_url_resolved
        )

    def dispatch_step(self, step_id: UUID) -> str:
        try:
            result = self._celery.send_task(
                settings.ai_core_step_task, args=[str(step_id)], queue="ai"
            )
        except (KombuOperationalError, RedisError, OSError) as exc:
            raise AiQueueUnavailable("AI task queue is unavailable") from exc
        return str(result.id)

    def dispatch_render(self, job_id: UUID) -> str:
        try:
            result = self._celery.send_task(
                settings.ai_core_render_task, args=[str(job_id)], queue="render"
            )
        except (KombuOperationalError, RedisError, OSError) as exc:
            raise AiQueueUnavailable("Render task queue is unavailable") from exc
        return str(result.id)
