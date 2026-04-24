from __future__ import annotations

import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from shared.pipeline_log import celery_trace_headers, pipeline_event
from shared.schemas.render_api import RenderEnqueueBody, RenderEnqueueResponse
from worker.tasks import render_manim_scene

from backend.api.access import project_readable_by_user
from backend.api.deps import get_content_store, get_job_store, get_request_user_id
from backend.core.config import settings
from backend.core.correlation import get_request_id
from backend.db.base import ContentStore
from backend.services.job_store import RedisRenderJobStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["render"])


@router.post("/{project_id}/render", summary="Enqueue Manim render job")
def enqueue_render(
    project_id: UUID,
    body: RenderEnqueueBody,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
    store: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
) -> JSONResponse:
    """Create a render job in Redis and enqueue Celery (Manim runs in worker only)."""
    project_readable_by_user(content, project_id, user_id)
    job_id = uuid4()
    trace_id = get_request_id()
    webhook = str(body.webhook_url) if body.webhook_url is not None else None
    try:
        store.create_queued_job(
            job_id=job_id,
            project_id=project_id,
            scene_id=body.scene_id,
            job_type=body.render_type,
            render_quality=body.quality,
            webhook_url=webhook,
            docker_image_tag=settings.worker_image_tag,
        )
        pipeline_event(
            "api.render",
            "job_queued",
            "Render job stored in Redis",
            trace_id=trace_id,
            job_id=str(job_id),
            project_id=str(project_id),
            scene_id=str(body.scene_id),
            details={"render_type": body.render_type, "quality": body.quality},
        )
    except RedisError:
        logger.exception("Redis failure while creating render job")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": {"code": "redis_unavailable", "message": "Job store unavailable"}},
        )

    try:
        render_manim_scene.apply_async(
            args=[str(job_id)],
            headers=celery_trace_headers(trace_id),
        )
        pipeline_event(
            "api.render",
            "celery_enqueued",
            "render_manim_scene dispatched",
            trace_id=trace_id,
            job_id=str(job_id),
        )
    except Exception:  # noqa: BLE001 — broker/kombu can raise varied connection errors
        logger.exception("Failed to enqueue Celery task (broker/redis)")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": {"code": "broker_unavailable", "message": "Queue unavailable"}},
        )

    payload = RenderEnqueueResponse(job_id=job_id).model_dump(mode="json")
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=payload)
