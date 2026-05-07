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
    name="manim_agent.synthesize_voice",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=60,
)
def synthesize_voice(self: Task, voice_job_id: str) -> str:
    """Celery entrypoint: Piper TTS runs in the `tts` queue worker only."""
    from worker.tts_runtime import execute_voice_job

    jid = UUID(voice_job_id)
    tid = trace_id_from_celery_request(self.request)
    token = pipeline_trace_id_var.set(tid) if tid else None
    try:
        logger.info("Starting TTS task voice_job_id=%s", jid)
        pipeline_event(
            "worker.tts",
            "task_start",
            "Celery TTS task started",
            voice_job_id=str(jid),
            trace_id=tid,
        )
        execute_voice_job(jid)
        pipeline_event(
            "worker.tts",
            "task_done",
            "Celery TTS task finished",
            voice_job_id=str(jid),
            trace_id=tid,
        )
    finally:
        if token is not None:
            pipeline_trace_id_var.reset(token)
    return voice_job_id
