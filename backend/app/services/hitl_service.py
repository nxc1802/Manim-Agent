from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from shared.schemas.hitl import AgentStep, AgentStepKind, AiRun

from app.core.config import settings
from app.db.base import ContentStore
from app.services.ai_queue import AiQueue, AiQueueUnavailable
from app.services.events import publish_project_event, step_event_payload
from app.services.hitl_store import SupabaseHitlStore
from app.services.project_lifecycle import reconcile_project_status

# All three generation stages are durable and user-visible. Idea sketching is
# deliberately lightweight and auto-advances; Storyboard remains the project
# HITL gate and Builder remains a per-scene run with internal review loops.
STEP_SEQUENCE: tuple[AgentStepKind, ...] = ("idea_sketcher", "storyboarder", "builder")
AUTO_PASS_KINDS: frozenset[AgentStepKind] = frozenset({"idea_sketcher"})
logger = logging.getLogger(__name__)
_STORYBOARD_CONTINUITY_VALUES = {"new_section", "continue_animation"}

PipelineLockFactory = Callable[[UUID, UUID | None], AbstractContextManager[None]]


def approval_output_error(step_kind: str, output: dict[str, Any]) -> str | None:
    """Validate durable user-facing output before changing approval state."""
    if step_kind == "idea_sketcher":
        for field in (
            "concept",
            "audience",
            "learning_goal",
            "visual_metaphor",
            "scope_notes",
        ):
            value = output.get(field)
            if not isinstance(value, str) or not value.strip():
                return f"Idea sketch requires non-empty {field}"
        key_points = output.get("key_points")
        if (
            not isinstance(key_points, list)
            or not 2 <= len(key_points) <= 6
            or not all(isinstance(item, str) and item.strip() for item in key_points)
        ):
            return "Idea sketch key_points must contain 2 to 6 non-empty strings"
        return None
    if step_kind == "storyboarder":
        scenes = output.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            return "Storyboard scenes must be a non-empty list"
        seen_orders: set[int] = set()
        for index, scene in enumerate(scenes, start=1):
            if not isinstance(scene, dict):
                return f"Storyboard scene {index} must be an object"
            scene_order = scene.get("scene_order")
            if (
                not isinstance(scene_order, int)
                or isinstance(scene_order, bool)
                or scene_order < 1
            ):
                return f"Storyboard scene {index} requires a positive integer scene_order"
            if scene_order in seen_orders:
                return f"Storyboard scene_order {scene_order} is duplicated"
            seen_orders.add(scene_order)
            for field in ("narration", "visual_action"):
                value = scene.get(field)
                if not isinstance(value, str) or not value.strip():
                    return f"Storyboard scene {index} requires non-empty {field}"
            continuity = scene.get("continuity", "new_section")
            if continuity not in _STORYBOARD_CONTINUITY_VALUES:
                return (
                    f"Storyboard scene {index} continuity must be one of "
                    "new_section or continue_animation"
                )
        return None
    if step_kind in {"builder", "code_reviewer", "visual_reviewer"}:
        code = output.get("manim_code")
        if not isinstance(code, str) or not code.strip():
            return "Builder output requires non-empty manim_code"
        return None
    return f"Unsupported approval step kind: {step_kind}"


def normalize_storyboard_output(output: dict[str, Any]) -> dict[str, Any]:
    """Fold adjacent continuation beats into one Manim scene.

    The master model explicitly labels visual continuity. Folding it before the
    durable storyboard is applied guarantees Builder receives a single canvas
    for incremental animations instead of recreating the prior state.
    """
    raw_scenes = output.get("scenes")
    if not isinstance(raw_scenes, list):
        return output
    normalized: list[dict[str, Any]] = []
    for raw_scene in sorted(raw_scenes, key=lambda item: int(item["scene_order"])):
        scene = dict(raw_scene)
        narration = str(scene["narration"]).strip()
        visual_action = str(scene["visual_action"]).strip()
        if scene.get("continuity", "new_section") == "continue_animation" and normalized:
            previous = normalized[-1]
            previous["narration"] = f"{previous['narration']}\n{narration}"
            previous["visual_action"] = (
                f"{previous['visual_action']}\n\n"
                "Continue on the same canvas with the existing objects; do not rebuild them.\n"
                f"{visual_action}"
            )
            continue
        scene["narration"] = narration
        scene["visual_action"] = visual_action
        scene["continuity"] = "new_section"
        normalized.append(scene)
    for index, scene in enumerate(normalized, start=1):
        scene["scene_order"] = index
    return {**output, "scenes": normalized}


class HitlPipelineService:
    def __init__(
        self,
        *,
        store: SupabaseHitlStore,
        content: ContentStore,
        queue: AiQueue,
        lock_factory: PipelineLockFactory | None = None,
    ) -> None:
        self.store = store
        self.content = content
        self.queue = queue
        self._lock_factory = lock_factory or (lambda _project_id, _scene_id: nullcontext())

    @staticmethod
    def _run_sort_key(run: AiRun) -> tuple[Any, str]:
        return run.created_at, str(run.id)

    def _target_runs(self, project_id: UUID, scene_id: UUID | None) -> list[AiRun]:
        return sorted(
            (
                run
                for run in self.store.list_runs(project_id)
                if run.scene_id == scene_id
            ),
            key=self._run_sort_key,
        )

    def _ensure_current_run(self, run: AiRun, *, allow_completed: bool = False) -> AiRun:
        target_runs = self._target_runs(run.project_id, run.scene_id)
        latest = target_runs[-1] if target_runs else None
        current = self.store.get_run(run.id)
        if (
            latest is None
            or latest.id != run.id
            or current is None
            or current.status in (
                {"failed", "cancelled"} if allow_completed else {"completed", "failed", "cancelled"}
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="AI run was superseded by a newer run for this target",
            )
        return current

    def _cancel_active_target_runs(
        self,
        *,
        project_id: UUID,
        scene_id: UUID | None,
        reason: str,
    ) -> None:
        for candidate in self._target_runs(project_id, scene_id):
            if candidate.status not in {"queued", "waiting_for_human"}:
                continue
            cancelled_steps = self.store.cancel_unfinished_steps(candidate.id, reason=reason)
            cancelled = self.store.update_run(candidate.id, status="cancelled")
            if cancelled is None:
                continue
            logger.info(
                "Superseded AI run project_id=%s scene_id=%s run_id=%s steps=%s",
                project_id,
                scene_id,
                candidate.id,
                len(cancelled_steps),
            )
            for cancelled_step in cancelled_steps:
                publish_project_event(
                    str(project_id),
                    "hitl.step.failed",
                    step_event_payload(cancelled_step, failure_stage="superseded_run"),
                )

    def start_project_run(
        self,
        *,
        project_id: UUID,
        user_id: UUID,
        prompt: str,
        hitl_enabled: bool = True,
    ) -> tuple[AiRun, AgentStep]:
        with self._lock_factory(project_id, None):
            project = self.content.get_project(project_id)
            if project is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
            self._cancel_active_target_runs(
                project_id=project_id,
                scene_id=None,
                reason="Cancelled because a newer Master run was started",
            )
            user_settings = self.content.get_user_settings(user_id)
            self.content.update_project(project_id, status="processing", video_url=None)
            run = self.store.create_run(
                project_id=project_id,
                scene_id=None,
                user_id=user_id,
                hitl_enabled=hitl_enabled,
            )
            initial_input = {
                "prompt": prompt,
                "project_title": project.title,
                "source_language": project.source_language,
                "agent_persona": user_settings.ai_agent_persona if user_settings else "Professional Educator",
                "template_selection": user_settings.template_selection if user_settings else "Educational",
            }
            step = self.store.create_step(
                run=run, sequence=1, kind="idea_sketcher", input_data=initial_input
            )
            publish_project_event(
                str(project_id),
                "hitl.step.queued",
                step_event_payload(step, run=run.model_dump(mode="json")),
            )
            self._dispatch_step_or_fail(run, step)
            return run, step

    def start_scene_run(
        self,
        *,
        project_id: UUID,
        scene_id: UUID,
        user_id: UUID,
        brief_override: str | None,
        hitl_enabled: bool = True,
    ) -> tuple[AiRun, AgentStep]:
        with self._lock_factory(project_id, scene_id):
            scene = self.content.get_scene(scene_id)
            if scene is None or scene.project_id != project_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
            project = self.content.get_project(project_id)
            if project is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
            self._cancel_active_target_runs(
                project_id=project_id,
                scene_id=scene_id,
                reason="Cancelled because a newer Builder run was started",
            )
            user_settings = self.content.get_user_settings(user_id)
            self.content.update_project(project_id, status="processing", video_url=None)
            run = self.store.create_run(
                project_id=project_id,
                scene_id=scene_id,
                user_id=user_id,
                hitl_enabled=hitl_enabled,
            )
            initial_input = {
                "brief": brief_override
                or scene.storyboard_text
                or project.description
                or project.title,
                "visual_action": scene.scene_dsl.get("visual_action") if scene.scene_dsl else "",
                "narration": scene.voice_script,
                "project_title": project.title,
                "source_language": project.source_language,
                "agent_persona": user_settings.ai_agent_persona if user_settings else "Professional Educator",
                "template_selection": user_settings.template_selection if user_settings else "Educational",
            }
            step = self.store.create_step(run=run, sequence=1, kind="builder", input_data=initial_input)
            # Regeneration immediately invalidates both render layers. Keeping the
            # previous scene video visible here would let a full-project concat
            # snapshot an artifact that no longer represents the active Builder run.
            self.content.update_scene(
                scene_id,
                generation_status="generating",
                video_url=None,
            )
            # Write after the scene mutation as well as before run creation so any
            # racing full-project compare-and-set is invalidated regardless of
            # which side of the scene update it observes.
            self.content.update_project(project_id, status="processing", video_url=None)
            publish_project_event(
                str(project_id),
                "hitl.step.queued",
                step_event_payload(step, run=run.model_dump(mode="json")),
            )
            self._dispatch_step_or_fail(run, step)
            return run, step

    def edit(
        self, *, run: AiRun, step: AgentStep, expected_revision: int, draft_output: dict[str, Any]
    ) -> AgentStep:
        with self._lock_factory(run.project_id, run.scene_id):
            self._ensure_current_run(run)
            updated = self.store.edit(
                step, draft_output=draft_output, expected_revision=expected_revision
            )
            if updated is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="Step was updated elsewhere"
                )
            publish_project_event(
                str(run.project_id), "hitl.step.edited", step_event_payload(updated)
            )
            return updated

    def approve(
        self,
        *,
        run: AiRun,
        step: AgentStep,
        expected_revision: int,
        final_output: dict[str, Any] | None,
    ) -> tuple[AgentStep, AgentStep | None]:
        with self._lock_factory(run.project_id, run.scene_id):
            self._ensure_current_run(run)
            output = final_output if final_output is not None else step.draft_output
            if not output:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Step has no output to approve"
                )
            validation_error = approval_output_error(step.kind, output)
            if validation_error:
                raise HTTPException(
                    status_code=422,
                    detail=validation_error,
                )
            durable_output = normalize_storyboard_output(output) if step.kind == "storyboarder" else output
            approved = self.store.approve(
                step, final_output=durable_output, expected_revision=expected_revision
            )
            if approved is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="Step was updated elsewhere"
                )
            self._apply_approved_output(run, approved)
            next_step = self._queue_next(run, approved)
            publish_project_event(
                str(run.project_id),
                "hitl.step.approved",
                step_event_payload(
                    approved,
                    next_step=next_step.model_dump(mode="json") if next_step else None,
                ),
            )
            return approved, next_step

    def auto_approve_and_continue(
        self,
        run: AiRun,
        step: AgentStep,
        *,
        target_lock_held: bool = False,
    ) -> tuple[AgentStep, AgentStep | None]:
        """Approve a generated step for explicit no-HITL/test runs only."""
        lock = (
            nullcontext()
            if target_lock_held
            else self._lock_factory(run.project_id, run.scene_id)
        )
        with lock:
            self._ensure_current_run(run)
            output = step.draft_output or {}
            validation_error = approval_output_error(step.kind, output)
            if validation_error:
                raise HTTPException(
                    status_code=422,
                    detail=validation_error,
                )
            durable_output = normalize_storyboard_output(output) if step.kind == "storyboarder" else output
            approved = self.store.approve(
                step,
                final_output=durable_output,
                expected_revision=step.revision,
            )
            if approved is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="Step could not be auto-approved"
                )
            self._apply_approved_output(run, approved)
            next_step = self._queue_next(run, approved)
            publish_project_event(
                str(run.project_id),
                "hitl.step.auto_approved",
                step_event_payload(
                    approved,
                    next_step=next_step.model_dump(mode="json") if next_step else None,
                ),
            )
            return approved, next_step

    def _apply_approved_output(self, run: AiRun, step: AgentStep) -> None:
        """Keep the editable, approved version as the scene's active artifact."""
        output = step.final_output or {}
        if step.kind == "idea_sketcher":
            return
        if step.kind == "storyboarder":
            scenes_data = output["scenes"]
            existing_scenes = self.content.get_project_scenes(step.project_id)
            existing_by_order = {scene.scene_order: scene for scene in existing_scenes}
            desired_orders = {int(scene["scene_order"]) for scene in scenes_data}
            for obsolete in existing_scenes:
                if obsolete.scene_order not in desired_orders:
                    self.content.delete_scene(obsolete.id)

            for s_data in scenes_data:
                from uuid import uuid4

                scene_order = int(s_data["scene_order"])
                narration = str(s_data["narration"]).strip()
                visual_action = str(s_data["visual_action"]).strip()
                existing = existing_by_order.get(scene_order)
                needs_builder = True
                if existing is None:
                    scene = self.content.create_scene(
                        scene_id=uuid4(),
                        project_id=step.project_id,
                        scene_order=scene_order,
                        storyboard_text=narration,
                        voice_script=narration,
                        storyboard_status="approved",
                    )
                    self.content.update_scene(
                        scene.id,
                        scene_dsl={"visual_action": visual_action},
                    )
                else:
                    current_action = (
                        existing.scene_dsl.get("visual_action")
                        if isinstance(existing.scene_dsl, dict)
                        else None
                    )
                    content_changed = (
                        existing.storyboard_text != narration
                        or existing.voice_script != narration
                        or current_action != visual_action
                    )
                    needs_builder = (
                        content_changed
                        or existing.generation_status in {"pending", "failed"}
                        or (
                            not existing.manim_code
                            and existing.generation_status != "generating"
                        )
                    )
                    update_fields: dict[str, Any] = {
                        "storyboard_text": narration,
                        "voice_script": narration,
                        "storyboard_status": "approved",
                        "scene_dsl": {"visual_action": visual_action},
                    }
                    if content_changed:
                        update_fields.update(
                            manim_code=None,
                            video_url=None,
                            generation_status="pending",
                        )
                    elif existing.generation_status == "failed":
                        update_fields["generation_status"] = "pending"
                    updated = self.content.update_scene(existing.id, **update_fields)
                    scene = updated or existing
                if needs_builder:
                    self.start_scene_run(
                        project_id=step.project_id,
                        scene_id=scene.id,
                        user_id=run.user_id,
                        brief_override=None,
                        hitl_enabled=run.hitl_enabled,
                    )
            reconcile_project_status(self.content, step.project_id)
            return

        if step.scene_id is None:
            return
        scene = self.content.get_scene(step.scene_id)
        if scene is None:
            return
        if step.kind == "builder":
            code = output.get("manim_code") or output.get("text")
            if isinstance(code, str) and code.strip():
                self.content.update_project(step.project_id, status="processing", video_url=None)
                self.content.update_scene(
                    step.scene_id,
                    manim_code=code,
                    manim_code_version=scene.manim_code_version + 1,
                    video_url=None,
                    generation_status="completed",
                )
                # A project render is a derivative of every scene render. Any
                # approved code change invalidates both layers immediately.
                self.content.update_project(step.project_id, video_url=None)
                reconcile_project_status(self.content, step.project_id)
        elif step.kind in {"code_reviewer", "visual_reviewer"}:
            # Review loop returns ReviewLoopResult with (possibly fixed) manim_code
            code = output.get("manim_code")
            if isinstance(code, str) and code.strip():
                self.content.update_scene(
                    step.scene_id,
                    manim_code=code,
                    manim_code_version=scene.manim_code_version + 1,
                )

    def reject(
        self, *, run: AiRun, step: AgentStep, expected_revision: int, feedback: str
    ) -> tuple[AgentStep, AgentStep]:
        with self._lock_factory(run.project_id, run.scene_id):
            self._ensure_current_run(run)
            rejected = self.store.reject(step, feedback=feedback, expected_revision=expected_revision)
            if rejected is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="Step was updated elsewhere"
                )
            retry = self.store.create_step(
                run=run,
                sequence=step.sequence + 1,
                kind=step.kind,
                input_data={
                    "feedback": feedback,
                    "previous_output": step.draft_output or {},
                    "retry_of": str(step.id),
                },
            )
            publish_project_event(
                str(run.project_id),
                "hitl.step.rejected",
                step_event_payload(rejected, retry=retry.model_dump(mode="json")),
            )
            self._dispatch_step_or_fail(run, retry)
            return rejected, retry

    def expire_stale_generation(self, *, run: AiRun, step: AgentStep) -> AgentStep:
        """Fail a queued or claimed step when its worker stops making progress.

        A missing worker can leave work in ``queued``; one that disappears
        after ``claim`` leaves it in ``generating``. Without a terminal
        callback, either state would otherwise be displayed indefinitely.
        This check runs while clients refresh a run and uses conditional store
        transitions, so an on-time worker callback safely wins the race.
        """
        if step.status not in {"queued", "generating"}:
            return step
        is_queued = step.status == "queued"
        timeout_seconds = (
            settings.ai_step_queue_stale_after_seconds
            if is_queued
            else settings.ai_step_stale_after_seconds
        )
        deadline = step.updated_at + timedelta(seconds=timeout_seconds)
        if datetime.now(tz=UTC) < deadline:
            return step

        with self._lock_factory(run.project_id, run.scene_id):
            # The caller may have loaded a stale snapshot immediately before a
            # worker heartbeat won the target lock. Re-read and re-check the
            # deadline so an active worker is never failed by that race.
            current = self.store.get_step(step.id)
            if current is None or current.status not in {"queued", "generating"}:
                return current or step
            current_timeout = (
                settings.ai_step_queue_stale_after_seconds
                if current.status == "queued"
                else settings.ai_step_stale_after_seconds
            )
            if datetime.now(tz=UTC) < current.updated_at + timedelta(seconds=current_timeout):
                return current
            step = current
            is_queued = step.status == "queued"
            error = (
                "AI worker did not claim the queued step before the timeout. "
                "Check the ai-worker service and retry the step."
                if is_queued
                else "AI worker stopped reporting progress before the generation timeout. "
                "Check the ai-worker service and retry the step."
            )
            failed = (
                self.store.fail_queued(step.id, error=error)
                if is_queued
                else self.store.fail(step.id, error=error)
            )
            if failed is None:
                return self.store.get_step(step.id) or step
            self.store.update_run(run.id, status="failed")
            if failed.scene_id:
                self.content.update_scene(failed.scene_id, generation_status="failed")
                reconcile_project_status(self.content, run.project_id)
            else:
                self.content.update_project(run.project_id, status="draft", video_url=None)
            publish_project_event(
                str(run.project_id),
                "hitl.step.failed",
                step_event_payload(
                    failed,
                    failure_stage="queue_timeout" if is_queued else "generation_timeout",
                ),
            )
            logger.warning(
                "Expired stale AI step run_id=%s step_id=%s status=%s age_seconds=%.1f",
                run.id,
                step.id,
                step.status,
                (datetime.now(tz=UTC) - step.updated_at).total_seconds(),
            )
            return failed

    def _dispatch_step_or_fail(self, run: AiRun, step: AgentStep) -> str:
        try:
            task_id = self.queue.dispatch_step(step.id)
            logger.info(
                "AI step dispatched run_id=%s step_id=%s task_id=%s",
                run.id,
                step.id,
                task_id,
            )
            return task_id
        except AiQueueUnavailable as exc:
            error = str(exc)[:4_000]
            failed = self.store.fail_queued(step.id, error=error)
            if failed is not None:
                self.store.update_run(run.id, status="failed")
                if failed.scene_id:
                    self.content.update_project(
                        run.project_id,
                        status="processing",
                        video_url=None,
                    )
                    self.content.update_scene(failed.scene_id, generation_status="failed")
                    self.content.update_project(run.project_id, video_url=None)
                    reconcile_project_status(self.content, run.project_id)
                else:
                    self.content.update_project(run.project_id, status="draft", video_url=None)
                publish_project_event(
                    str(run.project_id),
                    "hitl.step.failed",
                    step_event_payload(failed, failure_stage="queue_dispatch"),
                )
            else:
                logger.warning(
                    "AI step queue dispatch failed after status changed run_id=%s step_id=%s",
                    run.id,
                    step.id,
                )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI task queue unavailable",
            ) from exc

    def _queue_next(self, run: AiRun, step: AgentStep) -> AgentStep | None:
        if step.kind == "idea_sketcher":
            next_sequence = max(
                (item.sequence for item in self.store.list_steps(run.id)),
                default=step.sequence,
            ) + 1
            storyboarder = self.store.create_step(
                run=run,
                sequence=next_sequence,
                kind="storyboarder",
                input_data=dict(step.input),
            )
            self.store.update_run(run.id, status="queued")
            publish_project_event(
                str(run.project_id),
                "hitl.step.queued",
                step_event_payload(storyboarder),
            )
            self._dispatch_step_or_fail(run, storyboarder)
            return storyboarder

        # Storyboard produces child Builder runs; Builder's internal reviews
        # complete before this transition and supply verified source.
        self.store.update_run(run.id, status="completed")
        return None

    def rollback(self, *, run: AiRun, target_step_id: UUID) -> tuple[AiRun, AgentStep]:
        with self._lock_factory(run.project_id, run.scene_id):
            self._ensure_current_run(run, allow_completed=True)
            return self._rollback_locked(run=run, target_step_id=target_step_id)

    def _rollback_locked(self, *, run: AiRun, target_step_id: UUID) -> tuple[AiRun, AgentStep]:
        target_step = self.store.get_step(target_step_id)
        if target_step is None or target_step.run_id != run.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Target step not found in this run"
            )
        if target_step.status != "approved":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only an approved step can be rolled back",
            )

        invalidated_scene_ids: list[str] = []
        if target_step.kind in {"idea_sketcher", "storyboarder"}:
            # Project-stage approvals own every downstream storyboard/scene
            # artifact and child Builder run. Fence callbacks first, then
            # delete the derivatives so a later re-approval starts cleanly.
            scenes = self.content.get_project_scenes(run.project_id)
            scene_ids = {scene.id for scene in scenes}
            for child_run in self.store.list_runs(run.project_id):
                if child_run.scene_id not in scene_ids:
                    continue
                if child_run.status != "cancelled":
                    self.store.cancel_unfinished_steps(
                        child_run.id,
                        reason="Cancelled because the approved storyboard was rolled back",
                    )
                    self.store.update_run(child_run.id, status="cancelled")
            for scene in scenes:
                self.content.delete_scene(scene.id)
                invalidated_scene_ids.append(str(scene.id))
            self.content.update_project(run.project_id, status="draft", video_url=None)
        elif target_step.kind == "builder" and target_step.scene_id is not None:
            # The pending draft remains on the step, but it is no longer an
            # approved render input. Invalidate every derivative immediately.
            self.content.update_scene(
                target_step.scene_id,
                manim_code=None,
                video_url=None,
                generation_status="pending",
            )
            self.content.update_project(run.project_id, status="processing", video_url=None)
            invalidated_scene_ids.append(str(target_step.scene_id))

        # 1. Delete all steps after the target step
        self.store.delete_steps_after(run.id, target_step.sequence)

        # 2. Revert the target step to pending_review
        reverted_step = self.store.revert_step(target_step_id)
        if reverted_step is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Target step not found"
            )

        # 3. Revert run status
        updated_run = self.store.update_run(run.id, status="waiting_for_human")
        if updated_run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

        publish_project_event(
            str(run.project_id),
            "hitl.run.rolled_back",
            step_event_payload(
                reverted_step,
                run=updated_run.model_dump(mode="json"),
                target_step=reverted_step.model_dump(mode="json"),
                invalidated_scene_ids=invalidated_scene_ids,
            ),
        )
        return updated_run, reverted_step
