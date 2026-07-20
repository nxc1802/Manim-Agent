from __future__ import annotations

import logging
from uuid import UUID

from celery import Celery

from app.backend_client import BackendClient
from app.config import settings
from app.renderer import render_full_project, render_manim_code
from app.step_executor import StepExecutor

logger = logging.getLogger(__name__)

celery_app = Celery("ai_core", broker=settings.celery_broker_url_resolved)
celery_app.conf.update(
    task_default_queue="ai",
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_routes={"ai_core.render_manim_scene": {"queue": "render"}},
)


@celery_app.task(
    name="ai_core.generate_hitl_step",
    bind=True,
    autoretry_for=(),
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=settings.ai_step_soft_time_limit_seconds,
    time_limit=settings.ai_step_time_limit_seconds,
)
def generate_hitl_step(self, step_id: str) -> None:  # noqa: ANN001
    _ = self
    client = BackendClient()
    identifier = UUID(step_id)
    logger.info("AI step started step_id=%s", identifier)
    try:
        work_item = client.claim_step(identifier)
        client.complete_step(identifier, StepExecutor().generate(work_item))
        logger.info("AI step completed step_id=%s", identifier)
    except Exception as exc:  # noqa: BLE001
        logger.exception("AI step failed step_id=%s", identifier)
        try:
            client.fail_step(identifier, str(exc))
        except Exception:  # noqa: BLE001
            logger.exception("AI step failure callback failed step_id=%s", identifier)
        raise


@celery_app.task(name="ai_core.render_manim_scene", bind=True, autoretry_for=(), acks_late=True)
def render_manim_scene(self, job_id: str) -> None:  # noqa: ANN001
    _ = self
    client = BackendClient()
    identifier = UUID(job_id)
    logger.info("Render job started job_id=%s", identifier)
    try:
        work_item = client.claim_render(identifier)
        if work_item.get("job_type") == "full_project":
            result = render_full_project(
                identifier,
                work_item.get("scenes", []),
                work_item.get("settings"),
                work_item.get("source_language"),
            )
            client.complete_render(identifier, result.asset_url, result.logs)
        else:
            client.complete_render(
                identifier,
                render_manim_code(
                    identifier,
                    str(work_item["manim_code"]),
                    work_item.get("settings"),
                    work_item.get("voice_script"),
                    work_item.get("source_language"),
                ),
            )
        logger.info("Render job completed job_id=%s", identifier)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Render job failed job_id=%s", identifier)
        try:
            client.fail_render(identifier, str(exc))
        except Exception:  # noqa: BLE001
            logger.exception("Render failure callback failed job_id=%s", identifier)
        raise
