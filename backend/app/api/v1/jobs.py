from __future__ import annotations

from pathlib import Path
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from shared.schemas.render_api import RenderJobStatusResponse
from shared.schemas.storage_api import SignedVideoUrlResponse

from app.api.access import project_readable_by_user
from app.api.deps import ContentStore, get_content_store, get_job_store, get_request_user_id
from app.core.config import settings
from app.services.job_store import RedisRenderJobStore
from app.services.supabase_storage_rest import sign_storage_object_read_url

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
    content: ContentStore = Depends(get_content_store),  # noqa: B008
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
    expected_prefix = f"supabase://{settings.supabase_storage_bucket.strip()}/"
    if not job.asset_url or not job.asset_url.startswith(expected_prefix):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job has no Supabase Storage artifact",
        )
    object_path = job.asset_url.removeprefix(expected_prefix).lstrip("/")
    if not object_path or ".." in object_path.split("/"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job storage artifact is invalid",
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
            detail="Unable to sign the render artifact",
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
    content: ContentStore = Depends(get_content_store),  # noqa: B008
) -> RenderJobStatusResponse:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    project_readable_by_user(content, job.project_id, user_id)
    return RenderJobStatusResponse.model_validate(job.model_dump())


@router.get("/jobs/{job_id}/video", summary="Stream a local Compose render artifact")
def get_local_render_artifact(
    job_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
) -> FileResponse:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    project_readable_by_user(content, job.project_id, user_id)
    if job.status != "completed" or not job.asset_url or not job.asset_url.startswith("file://"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="No local artifact is available"
        )
    artifact_root = Path("/artifacts").resolve()
    try:
        path = Path(job.asset_url.removeprefix("file://")).resolve(strict=True)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Artifact path is not allowed"
        ) from exc
    if not path.is_relative_to(artifact_root) or not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Artifact path is not allowed"
        )
    return FileResponse(path, media_type="video/mp4", filename=f"{job_id}.mp4")
