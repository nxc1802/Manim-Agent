from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from redis.exceptions import RedisError
from shared.schemas.render_api import (
    RenderEnqueueBody,
    RenderEnqueueResponse,
    RenderJobStatusResponse,
)
from shared.schemas.storage_api import SignedVideoUrlResponse

from app.api.access import project_readable_by_user
from app.api.deps import ContentStore, get_content_store, get_job_store, get_request_user_id
from app.core.config import settings
from app.core.limiter import limiter
from app.services.ai_queue import AiQueue, AiQueueUnavailable
from app.services.events import publish_project_event
from app.services.job_store import RedisRenderJobStore
from app.services.render_snapshot import project_render_source, scene_render_source
from app.services.supabase_storage_rest import sign_storage_object_read_url

router = APIRouter(tags=["render"])
logger = logging.getLogger(__name__)


def _idempotency_scope(
    key: str,
    *,
    user_id: UUID,
    project_id: UUID,
    body: RenderEnqueueBody,
    source_fingerprint: str = "legacy",
) -> str:
    material = (
        f"{user_id}\0{project_id}\0{body.render_type}\0{body.scene_id}\0{body.quality}"
        f"\0{source_fingerprint}\0{key}"
    )
    return hashlib.sha256(material.encode()).hexdigest()


def _persisted_video_ref(
    *,
    project_id: UUID,
    scene_id: UUID | None,
    content: ContentStore,
) -> str:
    if scene_id is None:
        project = content.get_project(project_id)
        video_ref = project.video_url if project else None
    else:
        scene = content.get_scene(scene_id)
        if scene is None or scene.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
        video_ref = scene.video_url
    if not video_ref:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No rendered video is available",
        )
    return video_ref


@router.get(
    "/{project_id}/render-jobs",
    response_model=list[RenderJobStatusResponse],
    summary="List project render jobs for reload and multi-tab reconciliation",
)
def list_project_render_jobs(
    project_id: UUID,
    active: bool = False,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
    store: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
) -> list[RenderJobStatusResponse]:
    project_readable_by_user(content, project_id, user_id)
    return [
        RenderJobStatusResponse.model_validate(job.model_dump())
        for job in store.list_for_project(project_id, active_only=active)
    ]


@router.get(
    "/{project_id}/rendered-video-url",
    response_model=SignedVideoUrlResponse,
    summary="Sign the durable scene or project video reference",
)
def get_persisted_render_url(
    project_id: UUID,
    scene_id: UUID | None = None,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
) -> SignedVideoUrlResponse:
    project_readable_by_user(content, project_id, user_id)
    video_ref = _persisted_video_ref(
        project_id=project_id, scene_id=scene_id, content=content
    )
    expected_prefix = f"supabase://{settings.supabase_storage_bucket.strip()}/"
    if not video_ref.startswith(expected_prefix):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No Supabase Storage video is available",
        )
    object_path = video_ref.removeprefix(expected_prefix).lstrip("/")
    if not object_path or ".." in object_path.split("/"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Stored video reference is invalid",
        )
    try:
        url = sign_storage_object_read_url(object_path=object_path)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to sign the rendered video",
        ) from exc
    return SignedVideoUrlResponse(
        signed_url=url,
        expires_in_seconds=int(settings.supabase_signed_url_seconds),
    )


@router.get(
    "/{project_id}/rendered-video",
    summary="Stream the durable local scene or project video reference",
)
def get_persisted_local_render(
    project_id: UUID,
    scene_id: UUID | None = None,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
) -> FileResponse:
    project_readable_by_user(content, project_id, user_id)
    video_ref = _persisted_video_ref(
        project_id=project_id, scene_id=scene_id, content=content
    )
    if not video_ref.startswith("file://"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No local rendered video is available",
        )
    artifact_root = Path("/artifacts").resolve()
    try:
        path = Path(video_ref.removeprefix("file://")).resolve(strict=True)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rendered video is unavailable",
        ) from exc
    if not path.is_relative_to(artifact_root) or not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rendered video path is not allowed",
        )
    filename = f"{scene_id or project_id}.mp4"
    return FileResponse(path, media_type="video/mp4", filename=filename)


@router.post(
    "/{project_id}/render", status_code=status.HTTP_202_ACCEPTED, summary="Queue a Manim render"
)
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
    render_metadata: dict[str, object]
    if body.render_type == "full_project":
        if body.scene_id is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="full_project cannot have a scene_id")
        scenes = content.get_project_scenes(project_id)
        if not scenes or not any(scene.manim_code for scene in scenes):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The project has no generated Manim scene source to render",
            )
        render_metadata = project_render_source(scenes)
    else:
        if body.scene_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scene_id is required for scene render")
        scene = content.get_scene(body.scene_id)
        if scene is None or scene.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
        if not scene.manim_code or scene.generation_status != "completed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Scene has no completed, approved Manim code",
            )
        render_metadata = scene_render_source(scene)
    source_fingerprint = str(render_metadata["source_fingerprint"])
    scoped_idempotency_key: str | None = None
    if x_idempotency_key:
        if len(x_idempotency_key) > 512:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Idempotency-Key is too long",
            )
        scoped_idempotency_key = _idempotency_scope(
            x_idempotency_key,
            user_id=user_id,
            project_id=project_id,
            body=body,
            source_fingerprint=source_fingerprint,
        )
        existing = store.get_idempotent_job_id(scoped_idempotency_key)
        existing_job = store.get(existing) if existing else None
        if (
            existing_job is not None
            and existing_job.project_id == project_id
            and existing_job.status not in {"failed", "cancelled"}
        ):
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=RenderEnqueueResponse(job_id=existing_job.id).model_dump(mode="json"),
            )
    try:
        job_id = uuid4()
        job, created = store.get_or_create_active_job(
            job_id=job_id,
            project_id=project_id,
            scene_id=body.scene_id,
            job_type=body.render_type,
            render_quality=body.quality,
            docker_image_tag=None,
            metadata=render_metadata,
        )
    except (RedisError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to reserve a render job",
        ) from exc
    if not created:
        if scoped_idempotency_key:
            try:
                store.set_idempotent_job_id(scoped_idempotency_key, job.id)
            except RedisError:
                logger.exception("Unable to persist render idempotency key job_id=%s", job.id)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=RenderEnqueueResponse(job_id=job.id).model_dump(mode="json"),
        )

    # The queued hint must exist before Celery can publish started/progress
    # events from a fast worker.
    publish_project_event(
        str(project_id),
        "render.queued",
        {
            "job_id": str(job.id),
            "job": job.model_dump(mode="json"),
            "scene_id": str(body.scene_id) if body.scene_id else None,
        },
    )
    try:
        task_id = AiQueue().dispatch_render(job.id)
    except AiQueueUnavailable as exc:
        failed = None
        try:
            failed = store.transition(
                job.id,
                expected_status="queued",
                status="failed",
                error_code="queue_unavailable",
                logs=str(exc)[:4_000],
            )
        except RedisError:
            logger.exception("Unable to mark undispatched render failed job_id=%s", job.id)
        if failed is not None:
            publish_project_event(
                str(project_id),
                "render.failed",
                {
                    "job_id": str(failed.id),
                    "job": failed.model_dump(mode="json"),
                    "scene_id": str(failed.scene_id) if failed.scene_id else None,
                    "failure_stage": "queue_dispatch",
                },
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Queue unavailable"
        ) from exc
    if scoped_idempotency_key:
        try:
            store.set_idempotent_job_id(scoped_idempotency_key, job.id)
        except RedisError:
            # Dispatch already succeeded. Losing replay protection must not
            # misreport an accepted render as failed.
            logger.exception("Unable to persist render idempotency key job_id=%s", job_id)
    logger.info(
        "Render job dispatched project_id=%s job_id=%s task_id=%s",
        project_id,
        job.id,
        task_id,
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=RenderEnqueueResponse(job_id=job.id).model_dump(mode="json"),
    )
