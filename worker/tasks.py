from __future__ import annotations

import logging
from uuid import UUID

from worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="manim_agent.render_manim_scene")
def render_manim_scene(job_id: str) -> str:
    """Celery entrypoint: render is executed in worker processes only."""
    from worker.runtime import execute_render_job

    jid = UUID(job_id)
    logger.info("Starting render task job_id=%s", jid)
    execute_render_job(jid)
    return job_id
