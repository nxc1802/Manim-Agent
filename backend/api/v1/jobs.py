from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from shared.schemas.render_api import RenderJobStatusResponse
from shared.schemas.storage_api import SignedVideoUrlResponse

from backend.api.access import project_readable_by_user
from backend.api.deps import get_content_store, get_job_store, get_request_user_id
from backend.core.config import settings
from typing import Any
from backend.services.job_store import RedisRenderJobStore
from backend.services.supabase_storage_rest import sign_storage_object_read_url

router = APIRouter(tags=["jobs"])


@router.get(
    "/jobs/{job_id}/signed-video-url",
    response_model=SignedVideoUrlResponse,
    summary="Signed URL for final rendered mp4 (scene audio uses inline playback URLs).",
)
def get_job_signed_video_url(
    job_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
    content: Any = Depends(get_content_store),  # noqa: B008
) -> SignedVideoUrlResponse:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    project_readable_by_user(content, job.project_id, user_id)
    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is not completed yet",
        )
    object_path = f"{job.project_id}/renders/{job_id}.mp4"
    try:
        url = sign_storage_object_read_url(object_path=object_path)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return SignedVideoUrlResponse(
        signed_url=url,
        expires_in_seconds=int(settings.supabase_signed_url_seconds),
    )


@router.get("/jobs/{job_id}", summary="Get render job status")
def get_job(
    job_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
    content: Any = Depends(get_content_store),  # noqa: B008
) -> RenderJobStatusResponse:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    project_readable_by_user(content, job.project_id, user_id)
    return RenderJobStatusResponse.model_validate(job.model_dump())
