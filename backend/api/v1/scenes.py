from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from ai_engine.agents.builder import run_builder
from ai_engine.agents.director import run_director
from ai_engine.agents.planner import run_planner
from ai_engine.agents.sync_engine import run_sync_engine
from ai_engine.config import (
    default_agent_models_path,
    load_agent_models_yaml,
    load_builder_review_loop,
)
from ai_engine.llm_client import LLMClient
from ai_engine.orchestrator import run_single_review_round
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from redis.exceptions import RedisError
from shared.schemas.builder_api import GenerateCodeBody, GenerateCodeResponse
from shared.schemas.planner_output import PlannerOutput
from shared.schemas.render_job import RenderJob
from shared.schemas.review_pipeline import (
    BuilderReviewLoopRequest,
    BuilderReviewLoopResponse,
    ReviewRoundRequest,
    ReviewRoundResponse,
)
from shared.schemas.scene import Scene
from shared.schemas.sync_api import SyncEngineResponse
from shared.schemas.voice_api import VoiceEnqueueResponse, VoiceSynthesizeBody
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
from backend.services.builder_review_loop import run_builder_review_loop
from backend.services.code_sandbox import SandboxLimits, SandboxValidationError, validate_manim_code
from backend.services.content_store import RedisContentStore
from backend.services.frame_info import extract_end_of_play_jpeg_frame
from backend.services.job_store import RedisRenderJobStore
from backend.services.supabase_voice_rest import insert_voice_job_row
from backend.services.voice_job_store import RedisVoiceJobStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scenes"])


def _agent_models_path() -> Path:
    if settings.agent_models_yaml:
        return Path(settings.agent_models_yaml).expanduser()
    return default_agent_models_path()


def _local_mp4_from_render_job(job: RenderJob) -> Path | None:
    u = job.asset_url or ""
    if not u.startswith("file://"):
        return None
    p = Path(u.replace("file://", "", 1))
    return p if p.is_file() else None


class GenerateStoryboardBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief_override: str | None = Field(default=None, max_length=20_000)


@router.post(
    "/{scene_id}/generate-storyboard",
    response_model=Scene,
    summary="Director: storyboard draft",
)
def generate_storyboard(
    scene_id: UUID,
    body: GenerateStoryboardBody | None = None,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: RedisContentStore = Depends(get_content_store),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> Scene:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scene not found: {scene_id}",
        )
    project = project_readable_by_user(store, scene.project_id, user_id)
    if scene.storyboard_status == "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Storyboard already approved; refusing to regenerate",
        )

    params = get_agent_llm_params("director")
    text, _prompt_version = run_director(
        llm=llm,
        model=params.model,
        temperature=params.temperature,
        max_tokens=params.max_tokens,
        project_title=project.title,
        project_description=project.description,
        extra_brief=body.brief_override if body else None,
    )
    updated = store.update_scene(
        scene_id,
        storyboard_text=text,
        storyboard_status="pending_review",
    )
    assert updated is not None
    return updated


@router.post(
    "/{scene_id}/approve-storyboard",
    response_model=Scene,
    summary="HITL: approve storyboard",
)
def approve_storyboard(
    scene_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: RedisContentStore = Depends(get_content_store),  # noqa: B008
) -> Scene:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scene not found: {scene_id}",
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
            detail="Storyboard text is empty",
        )
    updated = store.update_scene(scene_id, storyboard_status="approved")
    assert updated is not None
    return updated


@router.post(
    "/{scene_id}/plan",
    response_model=Scene,
    summary="Planner: structured planner_output",
)
def run_scene_planner(
    scene_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: RedisContentStore = Depends(get_content_store),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> Scene:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scene not found: {scene_id}",
        )
    project_readable_by_user(store, scene.project_id, user_id)
    if scene.storyboard_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Storyboard must be approved before planning",
        )
    if not (scene.storyboard_text and scene.storyboard_text.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Storyboard text is missing",
        )

    params = get_agent_llm_params("planner")
    plan, _prompt_version = run_planner(
        llm=llm,
        model=params.model,
        temperature=params.temperature,
        max_tokens=params.max_tokens,
        storyboard_text=scene.storyboard_text,
    )
    updated = store.update_scene(
        scene_id,
        planner_output=plan.model_dump(mode="json"),
    )
    assert updated is not None
    return updated


@router.post(
    "/{scene_id}/generate-code",
    response_model=GenerateCodeResponse,
    summary="Builder: manim_code from planner_output",
)
def generate_scene_code(
    scene_id: UUID,
    body: GenerateCodeBody | None = None,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: RedisContentStore = Depends(get_content_store),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
    job_store: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
) -> GenerateCodeResponse:
    opts = body or GenerateCodeBody()
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scene not found: {scene_id}",
        )
    project_readable_by_user(store, scene.project_id, user_id)
    if scene.planner_output is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="planner_output is required; run POST .../plan first",
        )
    plan = PlannerOutput.model_validate(scene.planner_output)

    excerpt = scene.storyboard_text[:4000] if scene.storyboard_text else None
    params = get_agent_llm_params("builder")
    rt = get_runtime_limits()
    code, _pv, _bm = run_builder(
        llm=llm,
        model=params.model,
        temperature=params.temperature,
        max_tokens=params.max_tokens,
        planner=plan,
        sync_segments=scene.sync_segments,
        storyboard_excerpt=excerpt,
        request_timeout_seconds=rt.llm_timeout_seconds("builder"),
    )
    limits = SandboxLimits(max_bytes=settings.max_manim_code_bytes)
    try:
        validate_manim_code(code, limits=limits)
    except SandboxValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    prev = (scene.manim_code or "").strip()
    stripped = code.strip()
    next_ver = scene.manim_code_version + 1 if stripped != prev else scene.manim_code_version
    updated = store.update_scene(
        scene_id,
        manim_code=stripped,
        manim_code_version=next_ver,
    )
    assert updated is not None

    preview_job_id: UUID | None = None
    if opts.enqueue_preview:
        job_id = uuid4()
        try:
            job_store.create_queued_job(
                job_id=job_id,
                project_id=scene.project_id,
                scene_id=scene_id,
                job_type="preview",
                render_quality="720p",
                webhook_url=None,
                docker_image_tag=settings.worker_image_tag,
            )
        except RedisError as exc:
            logger.exception("Redis failure while creating preview render job")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Job store unavailable",
            ) from exc
        try:
            render_manim_scene.delay(str(job_id))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to enqueue Celery preview task")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Queue unavailable",
            ) from exc
        preview_job_id = job_id

    return GenerateCodeResponse(scene=updated, preview_job_id=preview_job_id)


@router.post(
    "/{scene_id}/voice",
    response_model=VoiceEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Voice: enqueue Piper TTS worker (segment-level timestamps, no STT)",
)
def enqueue_scene_voice(
    scene_id: UUID,
    body: VoiceSynthesizeBody | None = None,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: RedisContentStore = Depends(get_content_store),  # noqa: B008
    vstore: RedisVoiceJobStore = Depends(get_voice_job_store),  # noqa: B008
) -> VoiceEnqueueResponse:
    opts = body or VoiceSynthesizeBody()
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scene not found: {scene_id}",
        )
    project_readable_by_user(store, scene.project_id, user_id)
    if scene.storyboard_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Storyboard must be approved before voice synthesis",
        )
    text = (opts.voice_script_override or scene.voice_script or scene.storyboard_text or "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No voice script: set voice_script, storyboard_text, or voice_script_override",
        )
    job_id = uuid4()
    override = (
        opts.voice_script_override.strip()
        if opts.voice_script_override and opts.voice_script_override.strip()
        else None
    )
    metadata: dict[str, Any] = {
        "language": opts.language,
        "synthesis_text": text,
        "voice_script_override": override,
    }
    job = vstore.create_queued_job(
        job_id=job_id,
        project_id=scene.project_id,
        scene_id=scene_id,
        metadata=metadata,
        voice_engine="piper",
        docker_image_tag=settings.tts_worker_image_tag,
    )
    insert_voice_job_row(job)
    try:
        synthesize_voice.delay(str(job_id))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to enqueue Celery TTS task")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Queue unavailable",
        ) from exc
    return VoiceEnqueueResponse(
        voice_job_id=job_id,
        status="queued",
        poll_path=f"/v1/voice-jobs/{job_id}",
    )


@router.post(
    "/{scene_id}/sync-timeline",
    response_model=SyncEngineResponse,
    summary="Phase 8: Sync Engine merges voice timestamps + planner (API LLM).",
)
def run_sync_timeline(
    scene_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: RedisContentStore = Depends(get_content_store),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> SyncEngineResponse:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scene not found: {scene_id}",
        )
    project_readable_by_user(store, scene.project_id, user_id)
    if scene.planner_output is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="planner_output is required",
        )
    if not scene.timestamps:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="timestamps are required (run voice synthesis first)",
        )
    text = (scene.voice_script or scene.storyboard_text or "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="voice_script or storyboard_text is required for sync",
        )
    params = get_agent_llm_params("sync_engine")
    rt = get_runtime_limits()
    sync_obj, _pv, _sm = run_sync_engine(
        llm=llm,
        model=params.model,
        temperature=params.temperature,
        max_tokens=params.max_tokens,
        planner_output=scene.planner_output,
        voice_timestamps=scene.timestamps,
        voice_script=text,
        request_timeout_seconds=rt.llm_timeout_seconds("sync_engine"),
    )
    updated = store.update_scene(scene_id, sync_segments=sync_obj)
    assert updated is not None
    return SyncEngineResponse(scene=updated, sync_segments=sync_obj)


@router.post(
    "/{scene_id}/review-round",
    response_model=ReviewRoundResponse,
    summary="Phase 8 — Code then Visual review (LLM on API); early_stop only if both pass",
)
def run_review_round(
    scene_id: UUID,
    body: ReviewRoundRequest | None = None,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: RedisContentStore = Depends(get_content_store),  # noqa: B008
    job_store: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> ReviewRoundResponse:
    opts = body or ReviewRoundRequest()
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scene not found: {scene_id}",
        )
    project_readable_by_user(store, scene.project_id, user_id)
    code = (scene.manim_code or "").strip()
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="manim_code is empty",
        )
    preview_path: Path | None = None
    if opts.preview_job_id:
        try:
            jid = UUID(opts.preview_job_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="preview_job_id must be a UUID string",
            ) from exc
        job = job_store.get(jid)
        if job is None or job.scene_id != scene_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Render job not found for this scene",
            )
        if job.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Preview job is not completed yet",
            )
        preview_path = _local_mp4_from_render_job(job)
        if preview_path is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Preview asset must be a local file:// mp4 for visual review (dev/CI).",
            )

    yaml_data = load_agent_models_yaml(_agent_models_path())
    review_cfg = load_builder_review_loop(yaml_data)
    code_llm = get_agent_llm_params("code_reviewer")
    visual_llm = get_agent_llm_params("visual_reviewer")
    limits = SandboxLimits(max_bytes=settings.max_manim_code_bytes)
    rt = get_runtime_limits()
    return run_single_review_round(
        llm=llm,
        review_cfg=review_cfg,
        code_llm=code_llm,
        visual_llm=visual_llm,
        manim_code=code,
        sandbox_limits=limits,
        preview_video_path=preview_path,
        extract_preview_frame=extract_end_of_play_jpeg_frame,
        runtime_limits=rt,
    )


@router.post(
    "/{scene_id}/builder-review-loop",
    response_model=BuilderReviewLoopResponse,
    summary="Phase 8: full Builder ↔ review rounds with preview poll + HITL on max rounds",
)
def builder_review_loop_endpoint(
    scene_id: UUID,
    body: BuilderReviewLoopRequest | None = None,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: RedisContentStore = Depends(get_content_store),  # noqa: B008
    job_store: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> BuilderReviewLoopResponse:
    opts = body or BuilderReviewLoopRequest()
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scene not found: {scene_id}",
        )
    project_readable_by_user(store, scene.project_id, user_id)
    if scene.storyboard_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Storyboard must be approved",
        )
    if scene.planner_output is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="planner_output is required",
        )
    yaml_data = load_agent_models_yaml(_agent_models_path())
    rt = get_runtime_limits()
    poll_timeout = float(opts.preview_poll_timeout_seconds or rt.preview_poll_timeout_seconds)
    updated, report = run_builder_review_loop(
        scene_id=scene_id,
        store=store,
        job_store=job_store,
        llm=llm,
        yaml_data=yaml_data,
        runtime_limits=rt,
        preview_poll_timeout_seconds=poll_timeout,
    )
    return BuilderReviewLoopResponse(
        scene_id=str(updated.id),
        review_loop_status=updated.review_loop_status,
        report=report,
        rounds=list(report.get("rounds", [])),
    )


@router.post(
    "/{scene_id}/hitl-ack-builder-review",
    response_model=Scene,
    summary="Clear hitl_pending after human edits; sets review_loop_status to idle",
)
def hitl_ack_builder_review(
    scene_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: RedisContentStore = Depends(get_content_store),  # noqa: B008
) -> Scene:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scene not found: {scene_id}",
        )
    project_readable_by_user(store, scene.project_id, user_id)
    if scene.review_loop_status != "hitl_pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scene is not awaiting HITL for builder review",
        )
    updated = store.update_scene(scene_id, review_loop_status="idle")
    assert updated is not None
    return updated
