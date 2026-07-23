from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

import httpx
from celery import Celery

from app.backend_client import BackendClient
from app.config import settings
from app.renderer import render_full_project, render_manim_code
from app.step_executor import StepExecutor

logger = logging.getLogger(__name__)


def _remove_uploaded_local_artifact(
    local_asset_url: str,
    completed_job: dict[str, object],
) -> None:
    """Release worker disk only after Backend confirms durable Storage state."""
    if not local_asset_url.startswith("file://"):
        return
    persisted_asset_url = completed_job.get("asset_url")
    if not isinstance(persisted_asset_url, str) or not persisted_asset_url.startswith(
        "supabase://"
    ):
        return
    artifact_root = settings.artifacts_dir.resolve()
    try:
        local_path = Path(local_asset_url.removeprefix("file://")).resolve(strict=True)
        if not local_path.is_relative_to(artifact_root) or not local_path.is_file():
            logger.warning("Refused to clean render artifact outside ARTIFACTS_DIR")
            return
        local_path.unlink()
    except OSError as exc:
        # The durable callback already succeeded. Cleanup is best-effort and a
        # transient filesystem issue must not turn a completed render into a
        # failed/retried Celery task.
        logger.warning("Unable to clean uploaded local render artifact error=%s", exc)

celery_app = Celery("ai_core", broker=settings.celery_broker_url_resolved)
celery_app.conf.update(
    task_default_queue="ai",
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=settings.celery_max_tasks_per_child,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        "visibility_timeout": settings.celery_visibility_timeout_seconds,
    },
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
    identifier = UUID(step_id)
    logger.info("AI step started step_id=%s", identifier)
    with BackendClient() as client:
        try:
            work_item = client.claim_step(identifier)
        except Exception as exc:  # noqa: BLE001
            if (
                isinstance(exc, httpx.HTTPStatusError)
                and exc.response is not None
                and exc.response.status_code == 409
            ):
                logger.info(
                    "AI step claim skipped for inactive/superseded target step_id=%s", identifier
                )
                return
            logger.exception("AI step claim failed step_id=%s", identifier)
            raise

        try:
            result = StepExecutor().generate(work_item, backend_client=client)
            client.complete_step(identifier, result)
            logger.info("AI step completed step_id=%s", identifier)
        except Exception as exc:  # noqa: BLE001
            logger.exception("AI step failed step_id=%s", identifier)
            try:
                client.fail_step(identifier, str(exc))
            except Exception:  # noqa: BLE001
                logger.exception("AI step failure callback failed step_id=%s", identifier)
            raise


@celery_app.task(
    name="ai_core.render_manim_scene",
    bind=True,
    autoretry_for=(),
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=settings.render_soft_time_limit_seconds,
    time_limit=settings.render_time_limit_seconds,
)
def render_manim_scene(self, job_id: str) -> None:  # noqa: ANN001
    _ = self
    identifier = UUID(job_id)
    logger.info("Render job started job_id=%s", identifier)
    with BackendClient() as client:
        try:
            work_item = client.claim_render(identifier)
        except Exception as exc:  # noqa: BLE001
            if (
                isinstance(exc, httpx.HTTPStatusError)
                and exc.response is not None
                and exc.response.status_code == 409
            ):
                logger.info(
                    "Render job claim skipped for inactive/superseded target job_id=%s", identifier
                )
                return
            logger.exception("Render job claim failed job_id=%s", identifier)
            raise

        try:
            if work_item.get("job_type") == "full_project":
                result = render_full_project(
                    identifier,
                    work_item.get("scenes", []),
                    work_item.get("settings"),
                    work_item.get("source_language"),
                )
                completed_job = client.complete_render(identifier, result.asset_url, result.logs)
                _remove_uploaded_local_artifact(result.asset_url, completed_job)
            else:
                asset_url = render_manim_code(
                    identifier,
                    str(work_item["manim_code"]),
                    work_item.get("settings"),
                    work_item.get("voice_script"),
                    work_item.get("source_language"),
                )
                completed_job = client.complete_render(identifier, asset_url)
                _remove_uploaded_local_artifact(asset_url, completed_job)
            logger.info("Render job completed job_id=%s", identifier)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Render job failed job_id=%s", identifier)
            try:
                client.fail_render(identifier, str(exc))
            except Exception:  # noqa: BLE001
                logger.exception("Render failure callback failed job_id=%s", identifier)
            raise
