from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from shared.schemas.voice_api import VoiceJobStatusResponse

from backend.api.access import project_readable_by_user
from backend.api.deps import get_content_store, get_request_user_id, get_voice_job_store
from backend.db.base import ContentStore
from backend.services.voice_job_store import RedisVoiceJobStore

router = APIRouter(tags=["voice-jobs"])


@router.get(
    "/voice-jobs/{voice_job_id}",
    response_model=VoiceJobStatusResponse,
    summary="Poll Piper TTS job status and playback URL when completed",
)
def get_voice_job(
    voice_job_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    vstore: RedisVoiceJobStore = Depends(get_voice_job_store),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
) -> VoiceJobStatusResponse:
    job = vstore.get(voice_job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice job not found")
    project_readable_by_user(content, job.project_id, user_id)
    return VoiceJobStatusResponse.model_validate(job.model_dump())
