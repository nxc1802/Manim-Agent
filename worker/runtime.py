from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
from backend.core.config import settings
from backend.services.job_store import RedisRenderJobStore
from backend.services.redis_client import get_redis
from backend.services.supabase_pipeline_rest import insert_worker_service_audit_row

from worker.renderer import render_manim_scene_to_disk
from worker.supabase_storage import upload_render_artifact_if_configured

logger = logging.getLogger(__name__)


def execute_render_job(job_id: UUID) -> None:
    store = RedisRenderJobStore(get_redis())
    job = store.get(job_id)
    if job is None:
        logger.error("render job missing: %s", job_id)
        return

    store.update(
        job_id,
        status="rendering",
        started_at=datetime.now(tz=UTC),
        progress=5,
        logs="Starting Manim render...",
    )

    try:
        quality = job.render_quality or "720p"
        result = render_manim_scene_to_disk(
            job_id=job_id,
            job_type=job.job_type,
            quality=quality,
        )
        video_path = result.video_path
        remote_url = upload_render_artifact_if_configured(
            video_path=video_path,
            project_id=job.project_id,
            job_id=job_id,
        )
        asset_url = remote_url or video_path.resolve().as_uri()

        store.update(
            job_id,
            status="completed",
            progress=100,
            asset_url=asset_url,
            completed_at=datetime.now(tz=UTC),
            logs="Render completed.",
        )
        insert_worker_service_audit_row(
            audit_id=uuid4(),
            project_id=job.project_id,
            scene_id=job.scene_id,
            worker_kind="manim",
            worker_name=settings.worker_name,
            render_job_id=job_id,
            payload={
                "status": "completed",
                "command": result.command,
                "stdout_tail": result.stdout_tail,
                "stderr_tail": result.stderr_tail,
                "asset_url": asset_url,
                "video_path": str(video_path),
            },
        )

        if job.webhook_url:
            _post_webhook(
                job.webhook_url,
                job_id=job_id,
                job_status="completed",
                asset_url=asset_url,
                error=None,
            )
    except Exception as exc:  # noqa: BLE001 — surface failure to job record
        logger.exception("Render failed job_id=%s", job_id)
        store.update(
            job_id,
            status="failed",
            error_code="render_failed",
            completed_at=datetime.now(tz=UTC),
            logs=str(exc),
        )
        insert_worker_service_audit_row(
            audit_id=uuid4(),
            project_id=job.project_id,
            scene_id=job.scene_id,
            worker_kind="manim",
            worker_name=settings.worker_name,
            render_job_id=job_id,
            payload={"status": "failed", "error": str(exc)},
        )
        if job.webhook_url:
            _post_webhook(
                job.webhook_url,
                job_id=job_id,
                job_status="failed",
                asset_url=None,
                error=str(exc),
            )


def _post_webhook(
    url: str,
    *,
    job_id: UUID,
    job_status: str,
    asset_url: str | None,
    error: str | None,
) -> None:
    payload: dict[str, object] = {
        "job_id": str(job_id),
        "status": job_status,
        "asset_url": asset_url,
        "metadata": {"error": error, "worker": settings.worker_name},
    }
    try:
        httpx.post(url, json=payload, timeout=10.0)
    except Exception:
        logger.exception("Webhook POST failed job_id=%s url=%s", job_id, url)
