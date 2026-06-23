from __future__ import annotations

from backend.core.config import settings
from celery import Celery

celery_app = Celery(
    "manim_agent",
    broker=settings.celery_broker_url_resolved,
    include=["worker.tasks", "worker.tts_tasks", "worker.orchestrator_tasks"],
)

celery_app.conf.update(
    task_default_queue="render",
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "manim_agent.synthesize_voice": {"queue": "tts"},
        "manim_agent.run_orchestrator_loop": {"queue": "orchestrator"},
        "manim_agent.run_project_workflow": {"queue": "orchestrator"},
    },
    # Optimization: Disable Celery result storage to save Redis connections.
    # We manage job status manually in RedisRenderJobStore.
    task_ignore_result=True,
    result_persistent=False,
    broker_pool_limit=1,
)

from shared.pipeline_log import setup_pipeline_logging  # noqa: E402

setup_pipeline_logging(
    level=settings.log_level,
    supabase_url=settings.supabase_url,
    supabase_key=settings.supabase_service_role_key,
    redis_url=settings.redis_url,
    redis_prefix=settings.redis_prefix,
)
