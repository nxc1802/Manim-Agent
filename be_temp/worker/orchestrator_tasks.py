from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from celery import Task
from shared.constants import ReviewLoopMode
from shared.pipeline_log import (
    pipeline_event,
    pipeline_trace_id_var,
    trace_id_from_celery_request,
)

from worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="manim_agent.run_orchestrator_loop",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 1},
    retry_backoff=True,
)
def run_orchestrator_loop_task(
    self: Task,
    scene_id: str,
    preview_poll_timeout_seconds: float | None = None,
    mode: ReviewLoopMode = ReviewLoopMode.HITL,
    extra_rounds: int | None = None,
    use_primitives: bool = True,
) -> dict[str, Any]:
    """Celery task to run the builder-review loop in the background."""
    from pathlib import Path

    from ai_engine.config import default_agent_models_path, load_agent_models_yaml
    from ai_engine.orchestrator import run_builder_loop_phase
    from backend.api.deps import get_llm_client, get_runtime_limits
    from backend.core.config import settings
    from backend.db.content_store import get_content_store
    from backend.services.job_store import RedisRenderJobStore
    from backend.services.redis_client import get_redis

    sid = UUID(scene_id)
    tid = trace_id_from_celery_request(self.request)
    token = pipeline_trace_id_var.set(tid) if tid else None

    try:
        pipeline_event(
            "worker.orchestrator",
            "task_start",
            "Orchestrator loop task started",
            scene_id=str(sid),
            trace_id=tid,
        )

        store = get_content_store()
        job_store = RedisRenderJobStore(get_redis())
        llm = get_llm_client()
        rt = get_runtime_limits()

        yaml_path = (
            Path(settings.agent_models_yaml).expanduser()
            if settings.agent_models_yaml
            else default_agent_models_path()
        )
        yaml_data = load_agent_models_yaml(yaml_path)

        poll_timeout = preview_poll_timeout_seconds or rt.preview_poll_timeout_seconds

        import asyncio

        _scene, report = asyncio.run(
            run_builder_loop_phase(
                scene_id=sid,
                store=store,
                job_store=job_store,
                llm=llm,
                yaml_data=yaml_data,
                runtime_limits=rt,
                preview_poll_timeout_seconds=float(poll_timeout),
                mode=mode,
                extra_rounds=extra_rounds,
                use_primitives=use_primitives,
            )
        )

        pipeline_event(
            "worker.orchestrator",
            "task_done",
            "Orchestrator loop task finished",
            scene_id=str(sid),
            trace_id=tid,
        )
        return report

    finally:
        if token is not None:
            pipeline_trace_id_var.reset(token)
