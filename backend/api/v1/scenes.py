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
    run_builder_loop_phase,
    run_planning_phase,
    run_single_review_round,
    run_storyboard_phase,
)
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from shared.code_utils import extract_python_code
from shared.pipeline_log import pipeline_event
from shared.schemas.builder_api import GenerateCodeBody, GenerateCodeResponse
from shared.schemas.planner_output import PlannerOutput
from shared.schemas.render_job import RenderJob
from shared.schemas.review_pipeline import (
    BuilderReviewLoopRequest,
    BuilderReviewLoopResponse,
    HitlReviewLoopAckRequest,
    HitlReviewLoopAckResponse,
    ReviewRoundRequest,
    ReviewRoundResponse,
)
from shared.schemas.scene import Scene
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
from backend.services.code_sandbox import SandboxLimits, validate_manim_code
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
    # response_model=Scene, # Might return dict or model depending on updated return
    summary="Director: storyboard draft",
)
def generate_storyboard(
    scene_id: UUID,
    body: GenerateStoryboardBody | None = None,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: Any = Depends(get_content_store),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> Scene:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}")
    project = project_readable_by_user(store, scene.project_id, user_id)
    if scene.storyboard_status == "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Storyboard already approved")

    params = get_agent_llm_params("director")
    pipeline_event("api.scenes", "storyboard_start", "Director: generating storyboard", scene_id=str(scene_id))
    
    text, _pv = run_storyboard_phase(
        llm=llm,
        model=params.model,
        temperature=params.temperature,
        max_tokens=params.max_tokens,
        project_title=project.title,
        project_description=project.description,
        extra_brief=body.brief_override if body else None,
    )
    
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
    store: Any = Depends(get_content_store),  # noqa: B008
) -> Scene:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}"
        )
    project_readable_by_user(store, scene.project_id, user_id)
    updated = store.update_scene(scene_id, storyboard_status="approved")
    assert updated is not None
    return updated


@router.post("/{scene_id}/plan", response_model=Scene)
def run_scene_planner(
    scene_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: Any = Depends(get_content_store),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> Scene:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}")
    project_readable_by_user(store, scene.project_id, user_id)
    if scene.storyboard_status != "approved":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Storyboard not approved")

    params = get_agent_llm_params("planner")
    pipeline_event("api.scenes", "plan_start", "Planner: generating execution plan", scene_id=str(scene_id))
    
    plan, _pv = run_planning_phase(
        llm=llm,
        model=params.model,
        temperature=params.temperature,
        max_tokens=params.max_tokens,
        storyboard_text=scene.storyboard_text,
    )
    
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
    store: Any = Depends(get_content_store),  # noqa: B008
) -> Scene:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}")
    project_readable_by_user(store, scene.project_id, user_id)
    updated = store.update_scene(scene_id, plan_status="approved")
    assert updated is not None
    return updated


@router.post("/{scene_id}/approve-voice-script", response_model=Scene)
def approve_voice_script(
    scene_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: Any = Depends(get_content_store),  # noqa: B008
) -> Scene:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}")
    project_readable_by_user(store, scene.project_id, user_id)
    updated = store.update_scene(scene_id, voice_script_status="approved")
    assert updated is not None
    return updated


@router.post("/{scene_id}/generate-code", response_model=GenerateCodeResponse)
def generate_scene_code(
    scene_id: UUID,
    body: GenerateCodeBody | None = None,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: Any = Depends(get_content_store),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
    job_store: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
) -> GenerateCodeResponse:
    opts = body or GenerateCodeBody()
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}")
    project_readable_by_user(store, scene.project_id, user_id)
    if scene.planner_output is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="planner_output is required")
    
    plan = PlannerOutput.model_validate(scene.planner_output)
    excerpt = scene.storyboard_text[:4000] if scene.storyboard_text else None
    params = get_agent_llm_params("builder")
    rt = get_runtime_limits()
    raw_code, _pv, _bm = run_builder(
        llm=llm,
        model=params.model,
        temperature=params.temperature,
        max_tokens=params.max_tokens,
        planner=plan,
        sync_segments=scene.sync_segments,
        storyboard_excerpt=excerpt,
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
            job_id=job_id, project_id=scene.project_id, scene_id=scene_id,
            job_type="preview", render_quality="720p", docker_image_tag=settings.worker_image_tag
        )
        render_manim_scene.apply_async(args=[str(job_id)])
        preview_job_id = job_id

    return GenerateCodeResponse(scene=updated, preview_job_id=preview_job_id)


@router.post("/{scene_id}/voice", response_model=VoiceEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_scene_voice(
    scene_id: UUID,
    body: VoiceSynthesizeBody | None = None,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: Any = Depends(get_content_store),  # noqa: B008
    vstore: RedisVoiceJobStore = Depends(get_voice_job_store),  # noqa: B008
) -> VoiceEnqueueResponse:
    opts = body or VoiceSynthesizeBody()
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}")
    project_readable_by_user(store, scene.project_id, user_id)
    
    text = (opts.voice_script_override or scene.voice_script or scene.storyboard_text or "").strip()
    job_id = uuid4()
    job = vstore.create_queued_job(
        job_id=job_id, project_id=scene.project_id, scene_id=scene_id,
        metadata={"synthesis_text": text}, voice_engine="piper",
        docker_image_tag=settings.tts_worker_image_tag
    )
    insert_voice_job_row(job)
    synthesize_voice.apply_async(args=[str(job_id)])
    return VoiceEnqueueResponse(voice_job_id=job_id, status="queued", poll_path=f"/v1/voice-jobs/{job_id}")


@router.post("/{scene_id}/review-round", response_model=ReviewRoundResponse)
def run_review_round_endpoint(
    scene_id: UUID,
    body: ReviewRoundRequest | None = None,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: Any = Depends(get_content_store),  # noqa: B008
    job_store: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> ReviewRoundResponse:
    opts = body or ReviewRoundRequest()
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}")
    project_readable_by_user(store, scene.project_id, user_id)
    
    preview_path: Path | None = None
    if opts.preview_job_id:
        job = job_store.get(UUID(opts.preview_job_id))
        if job and job.status == "completed":
            preview_path = _local_mp4_from_render_job(job)

    yaml_data = load_agent_models_yaml(_agent_models_path())
    review_cfg = load_builder_review_loop(yaml_data)
    return run_single_review_round(
        llm=llm, review_cfg=review_cfg,
        code_llm=get_agent_llm_params("code_reviewer"),
        visual_llm=get_agent_llm_params("visual_reviewer"),
        manim_code=(scene.manim_code or "").strip(),
        sandbox_limits=SandboxLimits(max_bytes=settings.max_manim_code_bytes),
        preview_video_path=preview_path,
        extract_preview_frame=extract_end_of_play_jpeg_frame,
        runtime_limits=get_runtime_limits()
    )


@router.post("/{scene_id}/builder-review-loop", response_model=BuilderReviewLoopResponse)
def builder_review_loop_endpoint(
    scene_id: UUID,
    body: BuilderReviewLoopRequest | None = None,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: Any = Depends(get_content_store),  # noqa: B008
    job_store: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> BuilderReviewLoopResponse:
    opts = body or BuilderReviewLoopRequest()
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}")
    project_readable_by_user(store, scene.project_id, user_id)
    
    yaml_data = load_agent_models_yaml(_agent_models_path())
    rt = get_runtime_limits()
    updated, report = run_builder_loop_phase(
        scene_id=scene_id, store=store, job_store=job_store, llm=llm,
        yaml_data=yaml_data, runtime_limits=rt,
        preview_poll_timeout_seconds=float(opts.preview_poll_timeout_seconds or rt.preview_poll_timeout_seconds),
        mode=opts.mode
    )
    return BuilderReviewLoopResponse(
        scene_id=str(updated.id),
        review_loop_status=updated.review_loop_status,
        report=report,
        rounds=list(report.get("rounds", []))
    )


@router.post("/{scene_id}/hitl-ack-builder-review", response_model=HitlReviewLoopAckResponse)
def hitl_ack_builder_review(
    scene_id: UUID,
    body: HitlReviewLoopAckRequest,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: Any = Depends(get_content_store),  # noqa: B008
    job_store: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> HitlReviewLoopAckResponse:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}")
    project_readable_by_user(store, scene.project_id, user_id)
    
    if body.action == "revert":
        # Simplified revert logic in API for now, or move to orchestrator helper
        updated = store.update_scene(
            scene_id, review_loop_status="idle", plan_status="pending_review",
            voice_script_status="pending_review", manim_code_version=1
        )
        return HitlReviewLoopAckResponse(scene=updated, message="Reverted.")
    
    if body.action == "continue":
        updated, _report = run_builder_loop_phase(
            scene_id=scene_id, store=store, job_store=job_store, llm=llm,
            yaml_data=load_agent_models_yaml(_agent_models_path()),
            runtime_limits=get_runtime_limits(),
            preview_poll_timeout_seconds=get_runtime_limits().preview_poll_timeout_seconds,
            mode="hitl", extra_rounds=body.extra_rounds
        )
        return HitlReviewLoopAckResponse(scene=updated, message="Continued.")

    # stop action
    updated = store.update_scene(scene_id, review_loop_status="failed")
    return HitlReviewLoopAckResponse(scene=updated, message="Stopped.")
