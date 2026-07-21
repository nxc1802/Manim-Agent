from __future__ import annotations

from uuid import UUID

from celery import Celery
from kombu.exceptions import OperationalError as KombuOperationalError
from redis.exceptions import RedisError

from app.core.config import settings


class AiQueueUnavailable(RuntimeError):
    """The task broker did not accept a dispatch request."""


def check_worker_queues() -> tuple[bool, tuple[str, ...]]:
    """Return whether live Celery consumers cover both production queues."""
    celery_app = Celery("manim_backend_readiness", broker=settings.celery_broker_url_resolved)
    try:
        replies = celery_app.control.inspect(
            timeout=settings.readiness_timeout_seconds
        ).active_queues()
    except (KombuOperationalError, RedisError, OSError, TimeoutError):
        return False, ()

    active_queues: set[str] = set()
    if isinstance(replies, dict):
        for queues in replies.values():
            if not isinstance(queues, list):
                continue
            for queue in queues:
                if isinstance(queue, dict) and isinstance(queue.get("name"), str):
                    active_queues.add(queue["name"])
    queue_names = tuple(sorted(active_queues))
    return {"ai", "render"}.issubset(active_queues), queue_names


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
