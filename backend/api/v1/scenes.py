from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from ai_engine.agents.builder import run_builder
from ai_engine.config import (
    default_agent_models_path,
    load_agent_models_yaml,
    load_builder_review_loop,
)
from ai_engine.llm_client import LLMClient
from ai_engine.orchestrator import (
    run_planning_phase,
    run_storyboard_phase,
)
from ai_engine.utils.storage_helper import save_agent_interaction
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from shared.code_utils import extract_python_code
from shared.pipeline_log import pipeline_event
from shared.schemas.builder_api import GenerateCodeBody, GenerateCodeResponse
from shared.schemas.planner_output import PlannerOutput
from shared.schemas.review_pipeline import (
    BuilderReviewLoopRequest,
    BuilderReviewLoopResponse,
    HitlReviewLoopAckRequest,
    HitlReviewLoopAckResponse,
    ReviewRoundRequest,
    ReviewRoundResponse,
)
from shared.schemas.scene import Scene, SceneUpdate
from shared.schemas.voice_api import VoiceEnqueueResponse, VoiceSynthesizeBody
from worker.orchestrator_tasks import run_orchestrator_loop_task
from worker.tasks import render_manim_scene
from worker.tts_tasks import synthesize_voice

from backend.api.access import project_readable_by_user
from backend.api.deps import (
    get_agent_llm_params,
    get_content_store,
    get_job_store,
    get_llm_client,
    get_request_user_id,
    get_runtime_limits,
    get_voice_job_store,
)
from backend.core.config import settings
from backend.core.limiter import limiter
from backend.db.base import ContentStore
from backend.services.code_sandbox import SandboxLimits, validate_manim_code
from backend.services.job_store import RedisRenderJobStore
from backend.services.supabase_voice_rest import insert_voice_job_row
from backend.services.sync_engine_logic import align_beats_to_audio
from backend.services.voice_job_store import RedisVoiceJobStore

logger = logging.getLogger(__name__)


router = APIRouter(tags=["scenes"])


@router.get("/{scene_id}", response_model=Scene, summary="Get scene by id")
def get_scene(
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
    return scene


@router.patch("/{scene_id}", response_model=Scene, summary="Update scene")
def update_scene(
    scene_id: UUID,
    body: SceneUpdate,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> Scene:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail=f"Scene not found: {scene_id}")
    project_readable_by_user(store, scene.project_id, user_id)

    update_data = body.model_dump(exclude_unset=True)
    updated = store.update_scene(scene_id, **update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Update failed")
    return updated


@router.delete("/{scene_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete scene")
def delete_scene(
    scene_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> None:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail=f"Scene not found: {scene_id}")
    project_readable_by_user(store, scene.project_id, user_id)
    store.delete_scene(scene_id)


def _agent_models_path() -> Path:
    if settings.agent_models_yaml:
        return Path(settings.agent_models_yaml).expanduser()
    return default_agent_models_path()


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
    store: ContentStore = Depends(get_content_store),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> Scene:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}"
        )
    project = project_readable_by_user(store, scene.project_id, user_id)
    if scene.storyboard_status == "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Storyboard already approved"
        )

    yaml_data = load_agent_models_yaml(_agent_models_path())
    params = get_agent_llm_params("director")

    # Use project-level target_scenes if set, else fallback to agent_models.yaml default
    target_scenes = project.target_scenes
    if target_scenes is None:
        target_scenes = yaml_data.get("agents", {}).get("director", {}).get("target_scenes")

    pipeline_event(
        "api.scenes", "storyboard_start", "Director: generating storyboard", scene_id=str(scene_id)
    )

    text, _pv, _metrics, _sys, _usr = await run_storyboard_phase(
        llm=llm,
        model=params.model,
        temperature=params.temperature,
        max_tokens=params.max_tokens,
        project_title=project.title,
        project_description=project.description,
        target_scenes=target_scenes,
        extra_brief=body.brief_override if body else None,
    )
    save_agent_interaction(scene.project_id, "director", "storyboard", _sys, _usr, text)

    updated = store.update_scene(scene_id, storyboard_text=text, storyboard_status="pending_review")
    pipeline_event(
        "api.scenes", "storyboard_ok", "Director: storyboard generated", scene_id=str(scene_id)
    )
    assert updated is not None
    return updated


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
    store: ContentStore = Depends(get_content_store),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> Scene:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}"
        )
    project = project_readable_by_user(store, scene.project_id, user_id)
    if scene.storyboard_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Storyboard must be approved before planning",
        )
    use_primitives = project.config.get("use_primitives", True)

    params = get_agent_llm_params("planner")
    rt = get_runtime_limits()
    pipeline_event(
        "api.scenes", "plan_start", "Planner: generating execution plan", scene_id=str(scene_id)
    )

    plan, _pv, _metrics, _sys, _usr = await run_planning_phase(
        llm=llm,
        model=params.model,
        temperature=params.temperature,
        max_tokens=params.max_tokens,
        storyboard_text=scene.storyboard_text or "",
        use_primitives=use_primitives,
        request_timeout_seconds=rt.llm_timeout_seconds("planner"),
    )
    save_agent_interaction(scene.project_id, "planner", "plan", _sys, _usr, plan)

    updated = store.update_scene(
        scene_id,
        planner_output=plan.model_dump(mode="json"),
        plan_status="pending_review",
        voice_script_status="pending_review",
    )
    pipeline_event("api.scenes", "plan_ok", "Planner: plan generated", scene_id=str(scene_id))
    assert updated is not None
    return updated


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
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> Scene:
    """Run deterministic Sync Engine to align beats to audio timestamps."""
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}"
        )
    project_readable_by_user(store, scene.project_id, user_id)

    if not scene.planner_output:
        raise HTTPException(status_code=400, detail="Missing execution plan for synchronization")
    if not scene.timestamps:
        raise HTTPException(
            status_code=400,
            detail="Missing voice timestamps for synchronization. Please run TTS first.",
        )

    from shared.schemas.voice_segments import VoiceSegmentTimestamps

    plan = PlannerOutput.model_validate(scene.planner_output)
    ts = VoiceSegmentTimestamps.model_validate(scene.timestamps)

    sync_segments = align_beats_to_audio(plan, ts)

    updated = store.update_scene(scene_id, sync_segments=sync_segments)
    pipeline_event("api.scenes", "sync_ok", "Sync: beats aligned to audio", scene_id=str(scene_id))
    assert updated is not None
    return updated


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
    store: ContentStore = Depends(get_content_store),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
    job_store: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
) -> GenerateCodeResponse:
    opts = body or GenerateCodeBody()
    logger.debug(f"generate_scene_code scene_id={scene_id} enqueue_preview={opts.enqueue_preview}")
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}"
        )
    project = project_readable_by_user(store, scene.project_id, user_id)
    if scene.storyboard_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Storyboard must be approved before planning",
        )
    use_primitives = project.config.get("use_primitives", True)

    plan = PlannerOutput.model_validate(scene.planner_output)
    excerpt = scene.storyboard_text[:4000] if scene.storyboard_text else None
    params = get_agent_llm_params("builder")
    rt = get_runtime_limits()
    raw_code, _pv, _bm, _sys, _usr = await run_builder(
        llm=llm,
        model=params.model,
        temperature=params.temperature,
        max_tokens=params.max_tokens,
        planner=plan,
        sync_segments=scene.sync_segments,
        storyboard_excerpt=excerpt,
        use_primitives=use_primitives,
        request_timeout_seconds=rt.llm_timeout_seconds("builder"),
    )
    code = extract_python_code(raw_code)
    limits = SandboxLimits(max_bytes=settings.max_manim_code_bytes)
    validate_manim_code(code, limits=limits)

    updated = store.update_scene(
        scene_id, manim_code=code.strip(), manim_code_version=scene.manim_code_version + 1
    )
    assert updated is not None

    preview_job_id: UUID | None = None
    if opts.enqueue_preview:
        job_id = uuid4()
        job_store.create_queued_job(
            job_id=job_id,
            project_id=scene.project_id,
            scene_id=scene_id,
            job_type="preview",
            render_quality="720p",
            webhook_url=None,
            docker_image_tag=settings.worker_image_tag,
        )
        render_manim_scene.apply_async(args=[str(job_id)])
        preview_job_id = job_id

    return GenerateCodeResponse(scene=updated, preview_job_id=preview_job_id)


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
    store: ContentStore = Depends(get_content_store),  # noqa: B008
    vstore: RedisVoiceJobStore = Depends(get_voice_job_store),  # noqa: B008
) -> VoiceEnqueueResponse:
    opts = body or VoiceSynthesizeBody()
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}"
        )
    project_readable_by_user(store, scene.project_id, user_id)
    if scene.storyboard_status != "approved":
        raise HTTPException(status_code=400, detail="Storyboard not approved")

    text = (opts.voice_script_override or scene.voice_script or scene.storyboard_text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Missing synthesis text (script or storyboard)")
    job_id = uuid4()
    metadata: dict[str, Any] = {"synthesis_text": text}
    if opts.voice_script_override:
        metadata["voice_script_override"] = opts.voice_script_override.strip()

    job = vstore.create_queued_job(
        job_id=job_id,
        project_id=scene.project_id,
        scene_id=scene_id,
        metadata=metadata,
        voice_engine="piper",
        docker_image_tag=settings.tts_worker_image_tag,
    )
    insert_voice_job_row(job)
    synthesize_voice.apply_async(args=[str(job_id)])
    return VoiceEnqueueResponse(
        voice_job_id=job_id, status="queued", poll_path=f"/v1/voice-jobs/{job_id}"
    )


@router.post("/{scene_id}/review-round", response_model=ReviewRoundResponse)
async def run_review_round_endpoint(
    scene_id: UUID,
    body: ReviewRoundRequest | None = None,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
    job_store: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> ReviewRoundResponse:
    opts = body or ReviewRoundRequest()
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}"
        )
    project_readable_by_user(store, scene.project_id, user_id)

    preview_path: Path | None = None
    if opts.preview_job_id:
        job = job_store.get(opts.preview_job_id)
        if job and job.status == "completed":
            preview_path = store.resolve_asset_local_path(job.asset_url)

    yaml_data = load_agent_models_yaml(_agent_models_path())
    review_cfg = load_builder_review_loop(yaml_data)
    from ai_engine.orchestrator import run_single_review_round_ex

    from backend.services.frame_info import extract_frame_at_timestamp

    resp, _prompts = await run_single_review_round_ex(
        llm=llm,
        review_cfg=review_cfg,
        code_llm=get_agent_llm_params("code_reviewer"),
        visual_llm=get_agent_llm_params("visual_reviewer"),
        manim_code=(scene.manim_code or "").strip(),
        sandbox_limits=SandboxLimits(max_bytes=settings.max_manim_code_bytes),
        preview_video_path=str(preview_path) if preview_path else None,
        extract_preview_frame=extract_frame_at_timestamp,
        sync_segments=scene.sync_segments if isinstance(scene.sync_segments, dict) else None,
        runtime_limits=get_runtime_limits(),
    )
    return resp


@router.post(
    "/{scene_id}/builder-review-loop",
    response_model=BuilderReviewLoopResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Orchestrator: start review loop",
    description=(
        "**Pipeline Orchestrator**: Chạy vòng lặp tự động bao gồm: Sinh code (Builder) "
        "→ Render (Worker) → Review (Code/Visual Reviewer). Vòng lặp sẽ lặp lại tối đa N lần "
        "hoặc dừng sớm nếu đạt yêu cầu chất lượng."
    ),
)
@limiter.limit("2/minute")  
def builder_review_loop_endpoint(
    request: Request,
    scene_id: UUID,
    body: BuilderReviewLoopRequest | None = None,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> BuilderReviewLoopResponse:
    opts = body or BuilderReviewLoopRequest()
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}"
        )
    project = project_readable_by_user(store, scene.project_id, user_id)
    if scene.storyboard_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Storyboard must be approved before planning",
        )
    use_primitives = project.config.get("use_primitives", True)

    # Update status to running immediately
    updated = store.update_scene(scene_id, review_loop_status="running")
    assert updated is not None

    # Trigger background task
    task = run_orchestrator_loop_task.apply_async(
        kwargs={
            "scene_id": str(scene_id),
            "preview_poll_timeout_seconds": opts.preview_poll_timeout_seconds,
            "mode": opts.mode,
            "use_primitives": use_primitives,
        }
    )

    return BuilderReviewLoopResponse(
        scene_id=scene_id, job_id=UUID(task.id), review_loop_status="running"
    )


@router.post("/{scene_id}/hitl-ack-builder-review", response_model=HitlReviewLoopAckResponse)
def hitl_ack_builder_review(
    scene_id: UUID,
    body: HitlReviewLoopAckRequest,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
    job_store: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> HitlReviewLoopAckResponse:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}"
        )
    project_readable_by_user(store, scene.project_id, user_id)

    if body.action == "revert":
        # Simplified revert logic in API for now, or move to orchestrator helper
        updated = store.update_scene(
            scene_id,
            review_loop_status="idle",
            plan_status="pending_review",
            voice_script_status="pending_review",
            manim_code_version=1,
        )
        assert updated is not None
        return HitlReviewLoopAckResponse(scene=updated, message="Reverted.")

    if body.action == "continue":
        project = project_readable_by_user(store, scene.project_id, user_id)
        use_primitives = project.config.get("use_primitives", True)

        # Update status to running immediately
        updated = store.update_scene(scene_id, review_loop_status="running")
        assert updated is not None

        task = run_orchestrator_loop_task.apply_async(
            kwargs={
                "scene_id": str(scene_id),
                "mode": "hitl",
                "extra_rounds": body.extra_rounds,
                "use_primitives": use_primitives,
            }
        )
        return HitlReviewLoopAckResponse(
            scene=updated, message=f"Continued in background (job_id={task.id})."
        )

    # stop action
    updated = store.update_scene(scene_id, review_loop_status="failed")
    assert updated is not None
    return HitlReviewLoopAckResponse(scene=updated, message="Stopped.")
