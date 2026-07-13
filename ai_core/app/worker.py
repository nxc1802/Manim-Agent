from __future__ import annotations

from uuid import UUID

from celery import Celery

from app.backend_client import BackendClient
from app.config import settings
from app.renderer import render_manim_code
from app.step_executor import StepExecutor

celery_app = Celery("ai_core", broker=settings.celery_broker_url_resolved)
celery_app.conf.update(
    task_default_queue="ai",
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_routes={"ai_core.render_manim_scene": {"queue": "render"}},
)


@celery_app.task(name="ai_core.generate_hitl_step", bind=True, autoretry_for=(), acks_late=True)
def generate_hitl_step(self, step_id: str) -> None:  # noqa: ANN001
    _ = self
    client = BackendClient()
    identifier = UUID(step_id)
    try:
        work_item = client.claim_step(identifier)
        client.complete_step(identifier, StepExecutor().generate(work_item))
    except Exception as exc:  # noqa: BLE001
        try:
            client.fail_step(identifier, str(exc))
        except Exception:  # noqa: BLE001
            pass
        raise


@celery_app.task(name="ai_core.render_manim_scene", bind=True, autoretry_for=(), acks_late=True)
def render_manim_scene(self, job_id: str) -> None:  # noqa: ANN001
    _ = self
    client = BackendClient()
    identifier = UUID(job_id)
    try:
        work_item = client.claim_render(identifier)
        client.complete_render(identifier, render_manim_code(identifier, str(work_item["manim_code"])))
    except Exception as exc:  # noqa: BLE001
        try:
            client.fail_render(identifier, str(exc))
        except Exception:  # noqa: BLE001
            pass
        raise
