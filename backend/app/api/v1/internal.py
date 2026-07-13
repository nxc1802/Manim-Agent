from __future__ import annotations

import hmac
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from shared.schemas.hitl import InternalStepCompleteRequest, InternalStepFailRequest

from app.api.deps import ContentStore, get_content_store, get_hitl_store, get_job_store
from app.core.config import settings
from app.services.events import publish_project_event
from app.services.hitl_store import SupabaseHitlStore
from app.services.job_store import RedisRenderJobStore

router = APIRouter(tags=["internal"])


def require_internal_service(x_internal_token: str | None = Header(None)) -> None:
    if not x_internal_token or not hmac.compare_digest(x_internal_token, settings.internal_service_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal service token")


@router.post("/hitl-steps/{step_id}/claim", dependencies=[Depends(require_internal_service)])
def claim_step(
    step_id: UUID,
    store: SupabaseHitlStore = Depends(get_hitl_store),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
) -> dict[str, Any]:
    step = store.claim(step_id)
    if step is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Step is not queueable")
    run = store.get_run(step.run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    project = content.get_project(step.project_id)
    scene = content.get_scene(step.scene_id)
    if project is None or scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project or scene not found")
    previous = [item.final_output for item in store.list_steps(run.id) if item.final_output]
    publish_project_event(str(step.project_id), "hitl.step.generating", {"step": step.model_dump(mode="json")})
    return {
        "step": step.model_dump(mode="json"),
        "project": project.model_dump(mode="json"),
        "scene": scene.model_dump(mode="json"),
        "approved_outputs": previous,
    }


@router.post("/hitl-steps/{step_id}/stream", dependencies=[Depends(require_internal_service)])
def stream_step(
    step_id: UUID,
    body: dict[str, Any],
    store: SupabaseHitlStore = Depends(get_hitl_store),  # noqa: B008
) -> dict[str, Any]:
    step = store.get_step(step_id)
    if step is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Step not found")
    content_delta = body.get("content_delta", "")
    if content_delta:
        publish_project_event(
            str(step.project_id),
            "hitl.step.generating",
            {"step": step.model_dump(mode="json"), "content_delta": content_delta}
        )
    return {"status": "ok"}


@router.post("/hitl-steps/{step_id}/complete", dependencies=[Depends(require_internal_service)])
def complete_step(
    step_id: UUID,
    body: InternalStepCompleteRequest,
    store: SupabaseHitlStore = Depends(get_hitl_store),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
) -> dict[str, Any]:
    step = store.complete(step_id, draft_output=body.draft_output)
    if step is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Step is not generating")

    run = store.get_run(step.run_id)
    if run is not None and _should_auto_approve(run, step):
        # Auto-approve and queue the next step
        from app.services.ai_queue import AiQueue
        from app.services.hitl_service import HitlPipelineService

        service = HitlPipelineService(store=store, content=content, queue=AiQueue())
        service.auto_approve_and_continue(run, step)
        return step.model_dump(mode="json")

    store.update_run(step.run_id, status="waiting_for_human")
    publish_project_event(str(step.project_id), "hitl.step.pending_review", {"step": step.model_dump(mode="json")})
    return step.model_dump(mode="json")


def _should_auto_approve(run: Any, step: Any) -> bool:
    """Decide if a completed step should be auto-approved."""
    from shared.schemas.hitl import AgentStepKind

    from app.services.hitl_service import AUTO_PASS_KINDS

    if not getattr(run, "hitl_enabled", True):
        return True  # Testing mode: auto-approve everything
    kind: AgentStepKind = step.kind
    return kind in AUTO_PASS_KINDS


@router.post("/hitl-steps/{step_id}/fail", dependencies=[Depends(require_internal_service)])
def fail_step(
    step_id: UUID,
    body: InternalStepFailRequest,
    store: SupabaseHitlStore = Depends(get_hitl_store),  # noqa: B008
) -> dict[str, Any]:
    step = store.fail(step_id, error=body.error)
    if step is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Step is not generating")
    store.update_run(step.run_id, status="failed")
    publish_project_event(str(step.project_id), "hitl.step.failed", {"step": step.model_dump(mode="json")})
    return step.model_dump(mode="json")


@router.post("/render-jobs/{job_id}/claim", dependencies=[Depends(require_internal_service)])
def claim_render_job(
    job_id: UUID,
    jobs: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
) -> dict[str, Any]:
    job = jobs.get(job_id)
    if job is None or job.status != "queued":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Render job is not queueable")
    if job.scene_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Render job has no scene")
    scene = content.get_scene(job.scene_id)
    if scene is None or not scene.manim_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Scene has no approved Manim code")
    running = jobs.update(job_id, status="rendering", progress=1, started_at=datetime.now(tz=UTC))
    assert running is not None
    publish_project_event(str(job.project_id), "render.started", {"job_id": str(job_id), "scene_id": str(job.scene_id)})
    return {"job": running.model_dump(mode="json"), "manim_code": scene.manim_code}


@router.post("/render-jobs/{job_id}/complete", dependencies=[Depends(require_internal_service)])
def complete_render_job(
    job_id: UUID,
    body: dict[str, Any],
    jobs: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
) -> dict[str, Any]:
    job = jobs.get(job_id)
    if job is None or job.status != "rendering":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Render job is not rendering")
    asset_url = body.get("asset_url")
    if not isinstance(asset_url, str) or not asset_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_url is required")
    updated = jobs.update(job_id, status="completed", progress=100, asset_url=asset_url, completed_at=datetime.now(tz=UTC))
    assert updated is not None
    publish_project_event(str(job.project_id), "render.completed", {"job": updated.model_dump(mode="json")})
    return updated.model_dump(mode="json")


@router.post("/render-jobs/{job_id}/fail", dependencies=[Depends(require_internal_service)])
def fail_render_job(
    job_id: UUID,
    body: dict[str, Any],
    jobs: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
) -> dict[str, Any]:
    job = jobs.get(job_id)
    if job is None or job.status != "rendering":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Render job is not rendering")
    error = str(body.get("error") or "Render failed")[:4_000]
    updated = jobs.update(job_id, status="failed", error_code="ai_core_render_failed", logs=error, completed_at=datetime.now(tz=UTC))
    assert updated is not None
    publish_project_event(str(job.project_id), "render.failed", {"job": updated.model_dump(mode="json")})
    return updated.model_dump(mode="json")
