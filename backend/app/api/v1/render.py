from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from shared.schemas.render_api import RenderEnqueueBody, RenderEnqueueResponse

from app.api.access import project_readable_by_user
from app.api.deps import ContentStore, get_content_store, get_job_store, get_request_user_id
from app.core.limiter import limiter
from app.services.ai_queue import AiQueue
from app.services.events import publish_project_event
from app.services.job_store import RedisRenderJobStore

router = APIRouter(tags=["render"])


@router.post("/{project_id}/render", status_code=status.HTTP_202_ACCEPTED, summary="Queue a Manim render")
@limiter.limit("5/minute")
def enqueue_render(
    project_id: UUID,
    body: RenderEnqueueBody,
    request: Request,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
    store: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
) -> JSONResponse:
    project_readable_by_user(content, project_id, user_id)
    if body.scene_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scene_id is required")
    scene = content.get_scene(body.scene_id)
    if scene is None or scene.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    if x_idempotency_key:
        existing = store.get_idempotent_job_id(x_idempotency_key)
        if existing:
            return JSONResponse(status_code=status.HTTP_200_OK, content=RenderEnqueueResponse(job_id=existing).model_dump(mode="json"))
    try:
        job_id = uuid4()
        store.create_queued_job(
            job_id=job_id, project_id=project_id, scene_id=body.scene_id,
            job_type=body.render_type, render_quality=body.quality,
            webhook_url=str(body.webhook_url) if body.webhook_url else None, docker_image_tag=None,
        )
        if x_idempotency_key:
            store.set_idempotent_job_id(x_idempotency_key, job_id)
        task_id = AiQueue().dispatch_render(job_id)
    except RedisError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Queue unavailable") from exc
    publish_project_event(str(project_id), "render.queued", {"job_id": str(job_id), "task_id": task_id, "scene_id": str(body.scene_id)})
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=RenderEnqueueResponse(job_id=job_id).model_dump(mode="json"))
