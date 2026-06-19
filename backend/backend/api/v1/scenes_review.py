from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from ai_engine.config import (
    default_agent_models_path,
    load_agent_models_yaml,
    load_builder_review_loop,
)
from ai_engine.llm_client import LLMClient
from fastapi import APIRouter, Depends, HTTPException, Request, status
from shared.schemas.review_pipeline import (
    BuilderReviewLoopRequest,
    BuilderReviewLoopResponse,
    HitlReviewLoopAckRequest,
    HitlReviewLoopAckResponse,
    ReviewRoundRequest,
    ReviewRoundResponse,
)
from worker.orchestrator_tasks import run_orchestrator_loop_task

from backend.api.access import project_readable_by_user
from backend.api.deps import (
    get_agent_llm_params,
    get_content_store,
    get_job_store,
    get_llm_client,
    get_request_user_id,
    get_runtime_limits,
)
from backend.core.config import settings
from backend.core.limiter import limiter
from backend.db.base import ContentStore
from backend.services.code_sandbox import SandboxLimits
from backend.services.job_store import RedisRenderJobStore

logger = logging.getLogger(__name__)

router = APIRouter()


def _agent_models_path() -> Path:
    if settings.agent_models_yaml:
        return Path(settings.agent_models_yaml).expanduser()
    return default_agent_models_path()


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
