from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from shared.schemas.builder_api import GenerateCodeBody, GenerateCodeResponse
from shared.schemas.scene import Scene
from shared.schemas.voice_api import VoiceEnqueueResponse, VoiceSynthesizeBody

from backend.api.access import project_readable_by_user
from backend.api.deps import (
    get_content_store,
    get_request_user_id,
    get_scene_service,
)
from backend.core.limiter import limiter
from backend.db.base import ContentStore
from backend.services.scene_service import SceneService

logger = logging.getLogger(__name__)

router = APIRouter()


class GenerateStoryboardBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief_override: str | None = Field(default=None, max_length=20_000)


@router.post(
    "/{scene_id}/generate-storyboard",
    summary="Director: storyboard draft",
    description=(
        "**Director Agent**: Tạo bản thảo storyboard từ tiêu đề và mô tả dự án. "
        "Đây là bước thiết kế nội dung hình ảnh và lời thoại thô."
    ),
    responses={
        200: {
            "description": "Storyboard generated",
            "content": {
                "application/json": {
                    "example": {
                        "id": "...",
                        "storyboard_text": "...",
                        "storyboard_status": "pending_review",
                    }
                }
            },
        },
        404: {"description": "Scene not found"},
        409: {"description": "Storyboard already approved"},
    },
)
@limiter.limit("5/minute") 
async def generate_storyboard(
    request: Request,
    scene_id: UUID,
    body: GenerateStoryboardBody | None = None,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    service: SceneService = Depends(get_scene_service),  # noqa: B008
) -> Scene:
    try:
        return await service.generate_storyboard(
            scene_id, user_id, body.brief_override if body else None
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{scene_id}/approve-storyboard", response_model=Scene)
def approve_storyboard(
    scene_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> Scene:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}"
        )
    project_readable_by_user(store, scene.project_id, user_id)
    if scene.storyboard_status != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Scene is not awaiting storyboard approval (status={scene.storyboard_status})",
        )
    if not (scene.storyboard_text and scene.storyboard_text.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scene has empty storyboard text",
        )

    updated = store.update_scene(scene_id, storyboard_status="approved")
    assert updated is not None
    return updated


@router.post(
    "/{scene_id}/plan",
    response_model=Scene,
    summary="Planner: execution plan",
    description=(
        "**Planner Agent**: Chuyển đổi storyboard đã duyệt thành một kế hoạch thực thi chi tiết "
        "bao gồm các 'beats' (nhịp) và các 'primitives' (linh kiện đồ họa)."
    ),
    responses={
        200: {"description": "Plan generated"},
        400: {"description": "Storyboard not approved"},
        404: {"description": "Scene not found"},
    },
)
@limiter.limit("10/minute")  
async def run_scene_planner(
    request: Request,
    scene_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    service: SceneService = Depends(get_scene_service),  # noqa: B008
) -> Scene:
    try:
        return await service.run_planner(scene_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{scene_id}/approve-plan", response_model=Scene)
def approve_plan(
    scene_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> Scene:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}"
        )
    project_readable_by_user(store, scene.project_id, user_id)
    updated = store.update_scene(scene_id, plan_status="approved")
    assert updated is not None
    return updated


@router.post("/{scene_id}/approve-voice-script", response_model=Scene)
def approve_voice_script(
    scene_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> Scene:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}"
        )
    project_readable_by_user(store, scene.project_id, user_id)
    updated = store.update_scene(scene_id, voice_script_status="approved")
    assert updated is not None
    return updated


@router.post("/{scene_id}/sync-timeline", response_model=Scene)
def sync_timeline_endpoint(
    scene_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    service: SceneService = Depends(get_scene_service),  # noqa: B008
) -> Scene:
    """Run deterministic Sync Engine to align beats to audio timestamps."""
    try:
        return service.sync_timeline(scene_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/{scene_id}/generate-code",
    response_model=GenerateCodeResponse,
    summary="Builder: generate Manim code",
    description=(
        "**Builder Agent**: Chuyển đổi execution plan và dữ liệu đồng bộ thành "
        "mã nguồn Manim Python hoàn chỉnh."
    ),
)
@limiter.limit("5/minute") 
async def generate_scene_code(
    request: Request,
    scene_id: UUID,
    body: GenerateCodeBody | None = None,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    service: SceneService = Depends(get_scene_service),  # noqa: B008
) -> GenerateCodeResponse:
    opts = body or GenerateCodeBody()
    try:
        updated, job_id = await service.generate_code(
            scene_id, user_id, enqueue_preview=opts.enqueue_preview
        )
        return GenerateCodeResponse(scene=updated, preview_job_id=job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/{scene_id}/voice",
    response_model=VoiceEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="TTS: synthesize voice",
    description=(
        "**TTS Engine (Piper)**: Chuyển đổi kịch bản lời thoại thành âm thanh "
        "và tính toán thời gian (timestamps) cho từng từ/đoạn."
    ),
)
def enqueue_scene_voice(
    scene_id: UUID,
    body: VoiceSynthesizeBody | None = None,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    service: SceneService = Depends(get_scene_service),  # noqa: B008
) -> VoiceEnqueueResponse:
    opts = body or VoiceSynthesizeBody()
    try:
        job_id = service.enqueue_voice(scene_id, user_id, opts.voice_script_override)
        return VoiceEnqueueResponse(
            voice_job_id=job_id, status="queued", poll_path=f"/v1/voice-jobs/{job_id}"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
