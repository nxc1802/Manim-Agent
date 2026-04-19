from __future__ import annotations

import logging
from uuid import UUID

from worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="manim_agent.synthesize_voice")
def synthesize_voice(voice_job_id: str) -> str:
    """Celery entrypoint: Piper TTS runs in the `tts` queue worker only."""
    from worker.tts_runtime import execute_voice_job

    jid = UUID(voice_job_id)
    logger.info("Starting TTS task voice_job_id=%s", jid)
    execute_voice_job(jid)
    return voice_job_id
