from __future__ import annotations

import logging
from uuid import UUID

from celery import Task
from shared.pipeline_log import (
    pipeline_event,
    pipeline_trace_id_var,
    trace_id_from_celery_request,
)

from worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="manim_agent.render_manim_scene",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=60,
)
def render_manim_scene(self: Task, job_id: str) -> str:
    """Celery entrypoint: render is executed in worker processes only."""
    from worker.runtime import execute_render_job

    jid = UUID(job_id)
    tid = trace_id_from_celery_request(self.request)
    token = pipeline_trace_id_var.set(tid) if tid else None
    try:
        logger.info("Starting render task job_id=%s", jid)
        pipeline_event(
            "worker.render",
            "task_start",
            "Celery render task started",
            job_id=str(jid),
            trace_id=tid,
        )
        execute_render_job(jid)
        pipeline_event(
            "worker.render",
            "task_done",
            "Celery render task finished",
            job_id=str(jid),
            trace_id=tid,
        )
    finally:
        if token is not None:
            pipeline_trace_id_var.reset(token)
    return job_id
