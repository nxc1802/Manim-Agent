from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from shared.schemas.hitl import (
    AgentStep,
    AiRun,
    ApproveStepRequest,
    EditStepRequest,
    RejectStepRequest,
    StartAiRunRequest,
    StartProjectRunRequest,
    StartAiRunResponse,
    StepTransitionResponse,
)

from app.api.access import project_readable_by_user
from app.api.deps import ContentStore, get_content_store, get_hitl_store, get_request_user_id
from app.services.ai_queue import AiQueue
from app.services.hitl_service import HitlPipelineService
from app.services.hitl_store import SupabaseHitlStore

router = APIRouter(tags=["human-in-the-loop"])


def get_pipeline_service(
    hitl_store: SupabaseHitlStore = Depends(get_hitl_store),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
) -> HitlPipelineService:
    return HitlPipelineService(store=hitl_store, content=content, queue=AiQueue())


def _owned_run(store: SupabaseHitlStore, run_id: UUID, project_id: UUID, user_id: UUID) -> AiRun:
    run = store.get_run(run_id)
    if run is None or run.project_id != project_id or run.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI run not found")
    return run


def _run_step(store: SupabaseHitlStore, run: AiRun, step_id: UUID) -> AgentStep:
    step = store.get_step(step_id)
    if step is None or step.run_id != run.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI step not found")
    return step


@router.post("/{project_id}/generate-scenes", response_model=StartAiRunResponse, status_code=status.HTTP_202_ACCEPTED)
def generate_scenes(
    project_id: UUID,
    body: StartProjectRunRequest,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
    service: HitlPipelineService = Depends(get_pipeline_service),  # noqa: B008
) -> StartAiRunResponse:
    project_readable_by_user(content, project_id, user_id)
    run, first_step = service.start_project_run(
        project_id=project_id,
        user_id=user_id,
        prompt=body.prompt,
        hitl_enabled=body.hitl_enabled,
    )
    return StartAiRunResponse(run=run, first_step=first_step)


@router.post("/{project_id}/ai-runs", response_model=StartAiRunResponse, status_code=status.HTTP_202_ACCEPTED)
def start_ai_run(
    project_id: UUID,
    body: StartAiRunRequest,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
    service: HitlPipelineService = Depends(get_pipeline_service),  # noqa: B008
) -> StartAiRunResponse:
    project_readable_by_user(content, project_id, user_id)
    run, first_step = service.start_scene_run(
        project_id=project_id,
        scene_id=body.scene_id,
        user_id=user_id,
        brief_override=body.brief_override,
        hitl_enabled=body.hitl_enabled,
    )
    return StartAiRunResponse(run=run, first_step=first_step)


@router.get("/{project_id}/ai-runs", response_model=list[AiRun])
def list_ai_runs(
    project_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
    store: SupabaseHitlStore = Depends(get_hitl_store),  # noqa: B008
) -> list[AiRun]:
    project_readable_by_user(content, project_id, user_id)
    return [run for run in store.list_runs(project_id) if run.user_id == user_id]


@router.get("/{project_id}/ai-runs/{run_id}/steps", response_model=list[AgentStep])
def list_ai_steps(
    project_id: UUID,
    run_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
    store: SupabaseHitlStore = Depends(get_hitl_store),  # noqa: B008
) -> list[AgentStep]:
    project_readable_by_user(content, project_id, user_id)
    run = _owned_run(store, run_id, project_id, user_id)
    return store.list_steps(run.id)


@router.patch("/{project_id}/ai-runs/{run_id}/steps/{step_id}", response_model=AgentStep)
def edit_ai_step(
    project_id: UUID,
    run_id: UUID,
    step_id: UUID,
    body: EditStepRequest,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
    store: SupabaseHitlStore = Depends(get_hitl_store),  # noqa: B008
    service: HitlPipelineService = Depends(get_pipeline_service),  # noqa: B008
) -> AgentStep:
    project_readable_by_user(content, project_id, user_id)
    run = _owned_run(store, run_id, project_id, user_id)
    step = _run_step(store, run, step_id)
    return service.edit(run=run, step=step, expected_revision=body.expected_revision, draft_output=body.draft_output)


@router.post("/{project_id}/ai-runs/{run_id}/steps/{step_id}/approve", response_model=StepTransitionResponse)
def approve_ai_step(
    project_id: UUID,
    run_id: UUID,
    step_id: UUID,
    body: ApproveStepRequest,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
    store: SupabaseHitlStore = Depends(get_hitl_store),  # noqa: B008
    service: HitlPipelineService = Depends(get_pipeline_service),  # noqa: B008
) -> StepTransitionResponse:
    project_readable_by_user(content, project_id, user_id)
    run = _owned_run(store, run_id, project_id, user_id)
    step = _run_step(store, run, step_id)
    approved, next_step = service.approve(
        run=run, step=step, expected_revision=body.expected_revision, final_output=body.final_output
    )
    return StepTransitionResponse(step=approved, next_step=next_step)


@router.post("/{project_id}/ai-runs/{run_id}/steps/{step_id}/reject", response_model=StepTransitionResponse)
def reject_ai_step(
    project_id: UUID,
    run_id: UUID,
    step_id: UUID,
    body: RejectStepRequest,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
    store: SupabaseHitlStore = Depends(get_hitl_store),  # noqa: B008
    service: HitlPipelineService = Depends(get_pipeline_service),  # noqa: B008
) -> StepTransitionResponse:
    project_readable_by_user(content, project_id, user_id)
    run = _owned_run(store, run_id, project_id, user_id)
    step = _run_step(store, run, step_id)
    rejected, retry = service.reject(run=run, step=step, expected_revision=body.expected_revision, feedback=body.feedback)
    return StepTransitionResponse(step=rejected, next_step=retry)


@router.post("/{project_id}/ai-runs/{run_id}/rollback", response_model=dict)
def rollback_ai_run(
    project_id: UUID,
    run_id: UUID,
    body: dict,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
    store: SupabaseHitlStore = Depends(get_hitl_store),  # noqa: B008
    service: HitlPipelineService = Depends(get_pipeline_service),  # noqa: B008
) -> dict:
    from shared.schemas.hitl import RollbackRequest
    try:
        req = RollbackRequest.model_validate(body)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    
    project_readable_by_user(content, project_id, user_id)
    run = _owned_run(store, run_id, project_id, user_id)
    
    updated_run, target_step = service.rollback(run=run, target_step_id=req.target_step_id)
    return {"run": updated_run.model_dump(mode="json"), "target_step": target_step.model_dump(mode="json")}
