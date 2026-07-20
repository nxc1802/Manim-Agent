from __future__ import annotations

import hmac
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from shared.schemas.hitl import InternalStepCompleteRequest, InternalStepFailRequest

from app.api.deps import ContentStore, get_content_store, get_hitl_store, get_job_store
from app.core.config import settings
from app.services.events import publish_project_event, step_event_payload
from app.services.hitl_service import approval_output_error
from app.services.hitl_store import SupabaseHitlStore
from app.services.job_store import RedisRenderJobStore
from app.services.pipeline_lock import pipeline_target_lock
from app.services.project_lifecycle import reconcile_project_status
from app.services.render_snapshot import (
    job_source_fingerprint,
    project_render_source,
    scene_render_source,
)
from app.services.supabase_storage_rest import (
    sign_storage_object_read_url,
    upload_render_artifact,
)

router = APIRouter(tags=["internal"])


def require_internal_service(x_internal_token: str | None = Header(None)) -> None:
    if not x_internal_token or not hmac.compare_digest(
        x_internal_token, settings.internal_service_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal service token"
        )


def _require_current_active_run(store: SupabaseHitlStore, step: Any) -> Any:
    run = store.get_run(step.run_id)
    if run is None or run.status not in {"queued", "waiting_for_human"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Run is not active")
    target_runs = sorted(
        (
            item
            for item in store.list_runs(step.project_id)
            if item.scene_id == step.scene_id
        ),
        key=lambda item: (item.created_at, str(item.id)),
    )
    if not target_runs or target_runs[-1].id != run.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="AI run was superseded by a newer run for this target",
        )
    return run


def _current_render_source(content: ContentStore, job: Any) -> dict[str, Any]:
    if job.scene_id:
        scene = content.get_scene(job.scene_id)
        if (
            scene is None
            or scene.project_id != job.project_id
            or not scene.manim_code
            or scene.generation_status != "completed"
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Scene render source is no longer current",
            )
        return scene_render_source(scene)

    project = content.get_project(job.project_id)
    scenes = content.get_project_scenes(job.project_id)
    if project is None or not scenes or not any(scene.manim_code for scene in scenes):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project has no current Manim source for a final render",
        )
    return project_render_source(scenes)


def _matching_render_source(
    content: ContentStore,
    job: Any,
    *,
    allow_legacy_snapshot: bool = False,
) -> dict[str, Any]:
    current = _current_render_source(content, job)
    expected = job_source_fingerprint(job.metadata)
    if expected == "legacy" and allow_legacy_snapshot:
        return current
    if expected != current["source_fingerprint"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Render source changed after this job was queued",
        )
    return current


def _reject_stale_render_job(
    jobs: RedisRenderJobStore,
    job: Any,
    *,
    detail: str,
) -> None:
    updated = jobs.transition(
        job.id,
        expected_status=job.status,
        status="failed",
        error_code="stale_render_source",
        logs=detail[:4_000],
        completed_at=datetime.now(tz=UTC),
    )
    if updated is not None:
        publish_project_event(
            str(updated.project_id),
            "render.failed",
            {
                "job": updated.model_dump(mode="json"),
                "job_id": str(updated.id),
                "scene_id": str(updated.scene_id) if updated.scene_id else None,
                "failure_stage": "source_fence",
            },
        )
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _persist_render_asset(content: ContentStore, job: Any, asset_url: str) -> None:
    if job.scene_id:
        for _attempt in range(3):
            scene = content.get_scene(job.scene_id)
            if scene is None or scene.project_id != job.project_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Render target no longer exists",
                )
            expected = job_source_fingerprint(job.metadata)
            if expected == "legacy" or scene_render_source(scene)["source_fingerprint"] != expected:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Render source changed before the artifact could be published",
                )

            # Invalidate before and after the scene CAS. The second write fences
            # a full-project completion racing between this invalidation and the
            # scene update.
            project = content.update_project(job.project_id, video_url=None)
            if project is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Render project no longer exists",
                )
            saved = content.update_scene_if_current(
                job.scene_id,
                expected_updated_at=scene.updated_at,
                video_url=asset_url,
            )
            if saved is None:
                continue
            if content.update_project(job.project_id, video_url=None) is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Render project no longer exists",
                )
            return
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scene changed while the render artifact was being published",
        )

    for _attempt in range(3):
        # Read the project revision first. Every supported scene mutation clears
        # the project artifact afterwards, so this CAS either loses the race or
        # is invalidated by the mutation that won it.
        project = content.get_project(job.project_id)
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Render project no longer exists",
            )
        _matching_render_source(content, job)
        saved = content.update_project_if_current(
            job.project_id,
            expected_updated_at=project.updated_at,
            video_url=asset_url,
        )
        if saved is not None:
            return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Project changed while the render artifact was being published",
    )


def _render_worker_input_url(asset_url: str) -> str:
    if asset_url.startswith("file://"):
        artifact_root = Path("/artifacts").resolve()
        try:
            local_path = Path(asset_url.removeprefix("file://")).resolve(strict=True)
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Rendered scene artifact is unavailable",
            ) from exc
        if not local_path.is_relative_to(artifact_root) or not local_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Rendered scene artifact path is not allowed",
            )
        return f"file://{local_path}"
    if asset_url.startswith("supabase://"):
        expected_prefix = f"supabase://{settings.supabase_storage_bucket.strip()}/"
        if not asset_url.startswith(expected_prefix):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Rendered scene references an unexpected storage bucket",
            )
        object_path = asset_url.removeprefix(expected_prefix).lstrip("/")
        if not object_path or ".." in object_path.split("/"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Rendered scene has an invalid storage object path",
            )
        try:
            return sign_storage_object_read_url(
                object_path=object_path,
                expires_in_seconds=settings.internal_render_signed_url_seconds,
            )
        except (RuntimeError, httpx.HTTPError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Unable to authorize a scene artifact for concatenation",
            ) from exc
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Rendered scene uses an unsupported asset URL",
    )


@router.post("/hitl-steps/{step_id}/claim", dependencies=[Depends(require_internal_service)])
def claim_step(
    step_id: UUID,
    store: SupabaseHitlStore = Depends(get_hitl_store),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
) -> dict[str, Any]:
    queued_step = store.get_step(step_id)
    if queued_step is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Step not found")
    with pipeline_target_lock(queued_step.project_id, queued_step.scene_id):
        run = _require_current_active_run(store, queued_step)
        step = store.claim(step_id)
        if step is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Step is not queueable")
        project = content.get_project(step.project_id)
        scene = content.get_scene(step.scene_id) if step.scene_id else None
        if project is None or (step.scene_id is not None and scene is None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project or scene not found"
            )
        previous = [item.final_output for item in store.list_steps(run.id) if item.final_output]
        publish_project_event(
            str(step.project_id),
            "hitl.step.generating",
            step_event_payload(step),
        )
        user_settings = content.get_user_settings(project.user_id)
        return {
            "step": step.model_dump(mode="json"),
            "project": project.model_dump(mode="json"),
            "scene": scene.model_dump(mode="json") if scene else None,
            "settings": user_settings.model_dump(mode="json") if user_settings else None,
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
    run = store.get_run(step.run_id)
    if step.status != "generating" or run is None or run.status in {
        "completed",
        "failed",
        "cancelled",
    }:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Step is not generating")
    content_delta = body.get("content_delta", "")
    if content_delta:
        publish_project_event(
            str(step.project_id),
            "hitl.step.generating",
            step_event_payload(step, content_delta=content_delta),
        )
    review = body.get("review")
    if isinstance(review, dict):
        publish_project_event(
            str(step.project_id),
            "hitl.step.review",
            step_event_payload(step, review=review),
        )
    return {"status": "ok"}


@router.post("/hitl-steps/{step_id}/complete", dependencies=[Depends(require_internal_service)])
def complete_step(
    step_id: UUID,
    body: InternalStepCompleteRequest,
    store: SupabaseHitlStore = Depends(get_hitl_store),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
) -> dict[str, Any]:
    generating_step = store.get_step(step_id)
    if generating_step is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Step not found")
    with pipeline_target_lock(generating_step.project_id, generating_step.scene_id):
        run = _require_current_active_run(store, generating_step)
        step = store.complete(step_id, draft_output=body.draft_output)
        if step is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Step is not generating")

        auto_approval_failure = _auto_approval_failure(step.kind, body.draft_output)
        if _should_auto_approve(run, step) and auto_approval_failure:
            failed = store.fail_pending_review(step.id, error=auto_approval_failure)
            if failed is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Failed review result changed before it could be recorded",
                )
            store.update_run(step.run_id, status="failed")
            if failed.scene_id:
                content.update_project(failed.project_id, status="processing", video_url=None)
                content.update_scene(failed.scene_id, generation_status="failed")
                content.update_project(failed.project_id, video_url=None)
                reconcile_project_status(content, failed.project_id)
            else:
                content.update_project(failed.project_id, status="draft", video_url=None)
            publish_project_event(
                str(failed.project_id), "hitl.step.failed", step_event_payload(failed)
            )
            return failed.model_dump(mode="json")
        if _should_auto_approve(run, step):
            # The callback already owns the target lock, so the service uses its
            # no-op default lock while retaining the current-run assertion.
            from app.services.ai_queue import AiQueue
            from app.services.hitl_service import HitlPipelineService

            service = HitlPipelineService(
                store=store,
                content=content,
                queue=AiQueue(),
                lock_factory=pipeline_target_lock,
            )
            service.auto_approve_and_continue(run, step, target_lock_held=True)
            return step.model_dump(mode="json")

        store.update_run(step.run_id, status="waiting_for_human")
        publish_project_event(
            str(step.project_id),
            "hitl.step.pending_review",
            step_event_payload(step),
        )
        return step.model_dump(mode="json")


def _auto_approval_failure(step_kind: str, draft_output: dict[str, Any]) -> str | None:
    """Reject malformed or unreviewed outputs before unattended approval."""
    basic_error = approval_output_error(step_kind, draft_output)
    if basic_error:
        return f"{step_kind.replace('_', ' ').title()} auto-approval failed: {basic_error}"
    if step_kind in {"idea_sketcher", "storyboarder"}:
        return None
    auto_review = draft_output.get("auto_review")
    if not isinstance(auto_review, dict):
        return "Builder auto-review failed: auto_review result is missing"
    direct_error = auto_review.get("error") or auto_review.get("final_error")
    if direct_error:
        return f"Builder auto-review failed: {str(direct_error)[:3_900]}"
    if auto_review.get("passed") is not True:
        return "Builder auto-review failed: top-level passed must be true"
    for reviewer in ("code", "visual"):
        result = auto_review.get(reviewer)
        if not isinstance(result, dict):
            return f"Builder auto-review failed: {reviewer} review result is missing"
        reviewer_error = result.get("error") or result.get("final_error")
        if result.get("passed") is not True or reviewer_error:
            detail = reviewer_error or f"{reviewer} review did not pass"
            return f"Builder {reviewer} review failed: {str(detail)[:3_900]}"
    return None


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
    content: ContentStore = Depends(get_content_store),  # noqa: B008
) -> dict[str, Any]:
    queued_step = store.get_step(step_id)
    if queued_step is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Step not found")
    with pipeline_target_lock(queued_step.project_id, queued_step.scene_id):
        _require_current_active_run(store, queued_step)
        step = store.fail(step_id, error=body.error)
        if step is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Step is not generating")
        store.update_run(step.run_id, status="failed")
        if step.scene_id:
            content.update_project(step.project_id, status="processing", video_url=None)
            content.update_scene(step.scene_id, generation_status="failed")
            content.update_project(step.project_id, video_url=None)
            reconcile_project_status(content, step.project_id)
        else:
            content.update_project(step.project_id, status="draft", video_url=None)
        publish_project_event(
            str(step.project_id),
            "hitl.step.failed",
            step_event_payload(step),
        )
        return step.model_dump(mode="json")


@router.post("/render-jobs/{job_id}/claim", dependencies=[Depends(require_internal_service)])
def claim_render_job(
    job_id: UUID,
    jobs: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
) -> dict[str, Any]:
    job = jobs.get(job_id)
    if job is None or job.status != "queued":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Render job is not queueable"
        )
    try:
        source_metadata = _matching_render_source(
            content,
            job,
            allow_legacy_snapshot=True,
        )
    except HTTPException as exc:
        if exc.status_code == status.HTTP_409_CONFLICT:
            _reject_stale_render_job(jobs, job, detail=str(exc.detail))
        raise
    claimed_metadata = (
        source_metadata if job_source_fingerprint(job.metadata) == "legacy" else job.metadata
    )
    project = content.get_project(job.project_id)
    user_settings = content.get_user_settings(project.user_id) if project else None

    if job.job_type == "full_project":
        project_scenes = content.get_project_scenes(job.project_id)
        if not project_scenes or not any(scene.manim_code for scene in project_scenes):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The project has no generated Manim scene source to render",
            )
        latest_scenes = content.get_project_scenes(job.project_id)
        if project_render_source(latest_scenes)["source_fingerprint"] != claimed_metadata[
            "source_fingerprint"
        ]:
            _reject_stale_render_job(
                jobs,
                job,
                detail="Project render source changed while the job was being claimed",
            )
        running = jobs.transition(
            job_id,
            expected_status="queued",
            status="rendering",
            progress=1,
            started_at=datetime.now(tz=UTC),
            metadata=claimed_metadata,
        )
        if running is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Render job is not queueable"
            )
        publish_project_event(
            str(job.project_id),
            "render.started",
            {"job_id": str(job.id), "job": running.model_dump(mode="json"), "scene_id": None},
        )
        payload = running.model_dump(mode="json")
        payload["scenes"] = [
            {
                "scene_id": str(scene.id),
                "scene_order": scene.scene_order,
                "generation_status": scene.generation_status,
                "manim_code": scene.manim_code,
                "voice_script": scene.voice_script,
            }
            for scene in sorted(
                project_scenes,
                key=lambda item: (item.scene_order, str(item.id)),
            )
        ]
        payload["settings"] = user_settings.model_dump(mode="json") if user_settings else None
        payload["source_language"] = project.source_language if project else "en"
        return payload

    if job.scene_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Render job has no scene"
        )
    scene = content.get_scene(job.scene_id)
    if scene is None or not scene.manim_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Scene has no approved Manim code"
        )
    if scene_render_source(scene)["source_fingerprint"] != claimed_metadata[
        "source_fingerprint"
    ]:
        _reject_stale_render_job(
            jobs,
            job,
            detail="Scene render source changed while the job was being claimed",
        )
    running = jobs.transition(
        job_id,
        expected_status="queued",
        status="rendering",
        progress=1,
        started_at=datetime.now(tz=UTC),
        metadata=claimed_metadata,
    )
    if running is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Render job is not queueable"
        )
    publish_project_event(
        str(job.project_id),
        "render.started",
        {
            "job_id": str(job_id),
            "job": running.model_dump(mode="json"),
            "scene_id": str(job.scene_id),
        },
    )
    return {
        "job": running.model_dump(mode="json"),
        "manim_code": scene.manim_code,
        "settings": user_settings.model_dump(mode="json") if user_settings else None,
        "voice_script": scene.voice_script,
        "source_language": project.source_language if project else "en",
    }


@router.post("/render-jobs/{job_id}/complete", dependencies=[Depends(require_internal_service)])
def complete_render_job(
    job_id: UUID,
    body: dict[str, Any],
    jobs: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
    content: ContentStore = Depends(get_content_store),  # noqa: B008
) -> dict[str, Any]:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Render job not found")
    if job.status == "completed" and job.asset_url:
        # The durable write happened before the terminal Redis transition.
        # Replaying it would be harmful for scene jobs because persistence also
        # invalidates a newer full-project artifact before and after the CAS.
        return job.model_dump(mode="json")
    if job.status != "rendering":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Render job is not rendering"
        )
    # Avoid uploading an artifact that is already known to be stale. The
    # compare-and-set in _persist_render_asset closes changes during upload.
    try:
        _matching_render_source(content, job)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_409_CONFLICT:
            _reject_stale_render_job(jobs, job, detail=str(exc.detail))
        raise
    asset_url = body.get("asset_url")
    if not isinstance(asset_url, str) or not asset_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_url is required")
    if asset_url.startswith("file://"):
        artifact_root = Path("/artifacts").resolve()
        try:
            local_path = Path(asset_url.removeprefix("file://")).resolve(strict=True)
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Render artifact is unavailable"
            ) from exc
        if not local_path.is_relative_to(artifact_root) or not local_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Artifact path is not allowed"
            )
        if settings.supabase_url and settings.supabase_service_role_key:
            object_path = f"{job.project_id}/renders/{job_id}.mp4"
            try:
                upload_render_artifact(source_path=local_path, object_path=object_path)
            except (OSError, RuntimeError, httpx.HTTPError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to upload render"
                ) from exc
            asset_url = f"supabase://{settings.supabase_storage_bucket}/{object_path}"
    elif asset_url.startswith("supabase://"):
        expected_prefix = f"supabase://{settings.supabase_storage_bucket.strip()}/"
        object_path = asset_url.removeprefix(expected_prefix).lstrip("/")
        if (
            not asset_url.startswith(expected_prefix)
            or not object_path
            or ".." in object_path.split("/")
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Render artifact storage URL is invalid",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Render artifact URL scheme is unsupported",
        )
    # Persist the durable content URL first. The operation is idempotent, and
    # the Redis status remains rendering if the database write fails.
    try:
        _persist_render_asset(content, job, asset_url)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_409_CONFLICT:
            _reject_stale_render_job(jobs, job, detail=str(exc.detail))
        raise
    updated = jobs.transition(
        job_id,
        expected_status="rendering",
        status="completed",
        progress=100,
        asset_url=asset_url,
        logs=str(body.get("logs") or "")[:4_000] or None,
        completed_at=datetime.now(tz=UTC),
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Render job changed while completing"
        )
    publish_project_event(
        str(job.project_id),
        "render.completed",
        {
            "job": updated.model_dump(mode="json"),
            "job_id": str(updated.id),
            "scene_id": str(updated.scene_id) if updated.scene_id else None,
        },
    )
    return updated.model_dump(mode="json")


@router.post("/render-jobs/{job_id}/fail", dependencies=[Depends(require_internal_service)])
def fail_render_job(
    job_id: UUID,
    body: dict[str, Any],
    jobs: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
) -> dict[str, Any]:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Render job not found")
    if job.status == "failed":
        return job.model_dump(mode="json")
    if job.status not in {"queued", "rendering"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Render job cannot be failed"
        )
    error = str(body.get("error") or "Render failed")[:4_000]
    updated = jobs.transition(
        job_id,
        expected_status=job.status,
        status="failed",
        error_code="ai_core_render_failed",
        logs=error,
        completed_at=datetime.now(tz=UTC),
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Render job changed while failing"
        )
    publish_project_event(
        str(job.project_id),
        "render.failed",
        {
            "job": updated.model_dump(mode="json"),
            "job_id": str(updated.id),
            "scene_id": str(updated.scene_id) if updated.scene_id else None,
        },
    )
    return updated.model_dump(mode="json")
