from __future__ import annotations

from backend.core.config import settings
from celery import Celery

celery_app = Celery(
    "manim_agent",
    broker=settings.celery_broker_url_resolved,
    backend=settings.celery_result_backend_resolved,
    include=["worker.tasks", "worker.tts_tasks", "worker.orchestrator_tasks"],
)

celery_app.conf.update(
    task_default_queue="render",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_routes={"manim_agent.synthesize_voice": {"queue": "tts"}},
    # Optimize connection usage for cloud free tiers
    broker_pool_limit=1,
    redis_max_connections=5,
)

from shared.pipeline_log import setup_pipeline_logging  # noqa: E402

setup_pipeline_logging(level=settings.log_level, redis_url=settings.redis_url)
