from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from shared.schemas.hitl import AgentStep, AgentStepKind, AiRun

from app.db.base import ContentStore
from app.services.ai_queue import AiQueue
from app.services.events import publish_project_event
from app.services.hitl_store import SupabaseHitlStore

STEP_SEQUENCE: tuple[AgentStepKind, ...] = (
    "builder",
)

# Steps that always auto-approve (no human review regardless of hitl_enabled)
AUTO_PASS_KINDS: frozenset[AgentStepKind] = frozenset({
    "builder", "code_reviewer", "visual_reviewer",
})


class HitlPipelineService:
    def __init__(self, *, store: SupabaseHitlStore, content: ContentStore, queue: AiQueue) -> None:
        self.store = store
        self.content = content
        self.queue = queue

    def start_project_run(
        self,
        *,
        project_id: UUID,
        user_id: UUID,
        prompt: str,
        hitl_enabled: bool = True,
    ) -> tuple[AiRun, AgentStep]:
        project = self.content.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        
        # Pass None explicitly as a string representation of null or modify store.create_run signature?
        # Actually in create_run, it needs a valid UUID. Let's look at `create_run`.
        # In hitl_store.py `create_run` takes `scene_id: UUID | None`. Oh wait, I didn't update hitl_store.py yet.
        run = self.store.create_run(
            project_id=project_id, scene_id=None,
            user_id=user_id, hitl_enabled=hitl_enabled,
        )
        initial_input = {
            "prompt": prompt,
            "project_title": project.title,
            "source_language": project.source_language,
        }
        step = self.store.create_step(run=run, sequence=1, kind="storyboarder", input_data=initial_input)
        self.queue.dispatch_step(step.id)
        publish_project_event(str(project_id), "hitl.step.queued", {"run": run.model_dump(mode="json"), "step": step.model_dump(mode="json")})
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
        scene = self.content.get_scene(scene_id)
        if scene is None or scene.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
        project = self.content.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        run = self.store.create_run(
            project_id=project_id, scene_id=scene_id,
            user_id=user_id, hitl_enabled=hitl_enabled,
        )
        initial_input = {
            "brief": brief_override or scene.storyboard_text or project.description or project.title,
            "visual_action": scene.scene_dsl.get("visual_action") if scene.scene_dsl else "",
            "narration": scene.voice_script,
            "project_title": project.title,
            "source_language": project.source_language,
        }
        step = self.store.create_step(run=run, sequence=1, kind="builder", input_data=initial_input)
        self.queue.dispatch_step(step.id)
        publish_project_event(str(project_id), "hitl.step.queued", {"run": run.model_dump(mode="json"), "step": step.model_dump(mode="json")})
        return run, step

    def edit(self, *, run: AiRun, step: AgentStep, expected_revision: int, draft_output: dict[str, Any]) -> AgentStep:
        updated = self.store.edit(step, draft_output=draft_output, expected_revision=expected_revision)
        if updated is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Step was updated elsewhere")
        publish_project_event(str(run.project_id), "hitl.step.edited", {"step": updated.model_dump(mode="json")})
        return updated

    def approve(
        self,
        *,
        run: AiRun,
        step: AgentStep,
        expected_revision: int,
        final_output: dict[str, Any] | None,
    ) -> tuple[AgentStep, AgentStep | None]:
        output = final_output if final_output is not None else step.draft_output
        if not output:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Step has no output to approve")
        approved = self.store.approve(step, final_output=output, expected_revision=expected_revision)
        if approved is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Step was updated elsewhere")
        self._apply_approved_output(approved)
        next_step = self._queue_next(run, approved)
        publish_project_event(
            str(run.project_id),
            "hitl.step.approved",
            {"step": approved.model_dump(mode="json"), "next_step": next_step.model_dump(mode="json") if next_step else None},
        )
        return approved, next_step

    def auto_approve_and_continue(self, run: AiRun, step: AgentStep) -> tuple[AgentStep, AgentStep | None]:
        """Auto-approve a completed step and queue the next one.

        Called by the internal ``complete_step`` endpoint for steps that
        should not wait for human review (builder, code_reviewer,
        visual_reviewer, or when ``hitl_enabled=False``).
        """
        output = step.draft_output or {}
        approved = self.store.approve(step, final_output=output, expected_revision=step.revision)
        if approved is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Step could not be auto-approved")
        self._apply_approved_output(approved)
        next_step = self._queue_next(run, approved)
        publish_project_event(
            str(run.project_id),
            "hitl.step.auto_approved",
            {"step": approved.model_dump(mode="json"), "next_step": next_step.model_dump(mode="json") if next_step else None},
        )
        return approved, next_step

    def _apply_approved_output(self, step: AgentStep) -> None:
        """Keep the editable, approved version as the scene's active artifact."""
        output = step.final_output or {}
        if step.kind == "storyboarder":
            # output should be a JSON array of scenes under 'scenes' key
            scenes_data = output.get("scenes", [])
            for s_data in scenes_data:
                # Create scenes in DB
                from uuid import uuid4
                scene_id = uuid4()
                self.content.create_scene(
                    scene_id=scene_id,
                    project_id=step.project_id,
                    scene_order=s_data.get("scene_order", 0),
                    storyboard_text=s_data.get("narration", ""),
                    voice_script=s_data.get("narration", ""),
                    storyboard_status="approved"
                )
                self.content.update_scene(
                    scene_id,
                    scene_dsl={"visual_action": s_data.get("visual_action", "")}
                )
            return

        scene = self.content.get_scene(step.scene_id)
        if scene is None:
            return
        if step.kind == "builder":
            code = output.get("manim_code") or output.get("text")
            if isinstance(code, str) and code.strip():
                self.content.update_scene(
                    step.scene_id,
                    manim_code=code,
                    manim_code_version=scene.manim_code_version + 1,
                )
        elif step.kind in {"code_reviewer", "visual_reviewer"}:
            # Review loop returns ReviewLoopResult with (possibly fixed) manim_code
            code = output.get("manim_code")
            if isinstance(code, str) and code.strip():
                self.content.update_scene(
                    step.scene_id,
                    manim_code=code,
                    manim_code_version=scene.manim_code_version + 1,
                )

    def reject(self, *, run: AiRun, step: AgentStep, expected_revision: int, feedback: str) -> tuple[AgentStep, AgentStep]:
        rejected = self.store.reject(step, feedback=feedback, expected_revision=expected_revision)
        if rejected is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Step was updated elsewhere")
        retry = self.store.create_step(
            run=run,
            sequence=step.sequence + 1,
            kind=step.kind,
            input_data={"feedback": feedback, "previous_output": step.draft_output or {}, "retry_of": str(step.id)},
        )
        self.queue.dispatch_step(retry.id)
        publish_project_event(str(run.project_id), "hitl.step.rejected", {"step": rejected.model_dump(mode="json"), "retry": retry.model_dump(mode="json")})
        return rejected, retry

    def _queue_next(self, run: AiRun, step: AgentStep) -> AgentStep | None:
        # We simplified the pipeline.
        # storyboarder is single-step.
        # builder is single-step (auto-approves, code_reviewer is internal to AI Core).
        self.store.update_run(run.id, status="completed")
        return None
        input_data: dict[str, Any] = {
            "approved_output": step.final_output or {},
            "previous_step_id": str(step.id),
        }
        # Inject manim_code for reviewer steps
        if next_kind in {"code_reviewer", "visual_reviewer"}:
            approved_output = step.final_output or {}
            input_data["manim_code"] = approved_output.get("manim_code", "")
        next_step = self.store.create_step(
            run=run,
            sequence=step.sequence + 1,
            kind=next_kind,
            input_data=input_data,
        )
        self.store.update_run(run.id, status="queued")
        self.queue.dispatch_step(next_step.id)
        return next_step

    def rollback(self, *, run: AiRun, target_step_id: UUID) -> tuple[AiRun, AgentStep]:
        target_step = self.store.get_step(target_step_id)
        if target_step is None or target_step.run_id != run.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target step not found in this run")
        
        # 1. Delete all steps after the target step
        self.store.delete_steps_after(run.id, target_step.sequence)
        
        # 2. Revert the target step to pending_review
        reverted_step = self.store.revert_step(target_step_id)
        if reverted_step is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target step not found")
        
        # 3. Revert run status
        updated_run = self.store.update_run(run.id, status="waiting_for_human")
        if updated_run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
            
        publish_project_event(
            str(run.project_id),
            "hitl.run.rolled_back",
            {"run": updated_run.model_dump(mode="json"), "target_step": reverted_step.model_dump(mode="json")}
        )
        return updated_run, reverted_step
