from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.services.hitl_service import (
    AUTO_PASS_KINDS,
    STEP_SEQUENCE,
    HitlPipelineService,
    normalize_storyboard_output,
)
from fastapi import HTTPException
from shared.schemas.hitl import AgentStep, AiRun
from shared.schemas.project import Project
from shared.schemas.scene import Scene


class MemoryHitlStore:
    def __init__(self) -> None:
        self.runs: dict[UUID, AiRun] = {}
        self.steps: dict[UUID, AgentStep] = {}

    def create_run(
        self, *, project_id: UUID, scene_id: UUID | None, user_id: UUID, hitl_enabled: bool = True
    ) -> AiRun:
        now = datetime.now(UTC)
        run = AiRun(
            id=uuid4(),
            project_id=project_id,
            scene_id=scene_id,
            user_id=user_id,
            status="queued",
            hitl_enabled=hitl_enabled,
            created_at=now,
            updated_at=now,
        )
        self.runs[run.id] = run
        return run

    def get_run(self, run_id: UUID) -> AiRun | None:
        return self.runs.get(run_id)

    def list_runs(self, project_id: UUID) -> list[AiRun]:
        return [run for run in self.runs.values() if run.project_id == project_id]

    def get_step(self, step_id: UUID) -> AgentStep | None:
        return self.steps.get(step_id)

    def create_step(self, *, run: AiRun, sequence: int, kind, input_data):  # noqa: ANN001
        now = datetime.now(UTC)
        step = AgentStep(
            id=uuid4(),
            run_id=run.id,
            project_id=run.project_id,
            scene_id=run.scene_id,
            sequence=sequence,
            kind=kind,
            status="queued",
            input=input_data,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        self.steps[step.id] = step
        return step

    def update_run(self, run_id: UUID, *, status: str) -> AiRun:
        run = self.runs[run_id].model_copy(update={"status": status})
        self.runs[run_id] = run
        return run

    def list_steps(self, run_id: UUID) -> list[AgentStep]:
        return [s for s in self.steps.values() if s.run_id == run_id]

    def edit(self, step: AgentStep, *, draft_output, expected_revision: int):  # noqa: ANN001
        current = self.steps[step.id]
        if current.status != "pending_review" or current.revision != expected_revision:
            return None
        updated = current.model_copy(
            update={"draft_output": draft_output, "revision": expected_revision + 1}
        )
        self.steps[step.id] = updated
        return updated

    def approve(self, step: AgentStep, *, final_output, expected_revision: int):  # noqa: ANN001
        current = self.steps[step.id]
        if current.status != "pending_review" or current.revision != expected_revision:
            return None
        updated = current.model_copy(
            update={
                "status": "approved",
                "final_output": final_output,
                "revision": expected_revision + 1,
            }
        )
        self.steps[step.id] = updated
        return updated

    def reject(self, step: AgentStep, *, feedback: str, expected_revision: int):  # noqa: ANN001
        current = self.steps[step.id]
        if current.status != "pending_review" or current.revision != expected_revision:
            return None
        updated = current.model_copy(
            update={"status": "rejected", "error": feedback, "revision": expected_revision + 1}
        )
        self.steps[step.id] = updated
        return updated

    def claim(self, step_id: UUID) -> AgentStep | None:
        current = self.steps.get(step_id)
        if current is None or current.status != "queued":
            return None
        updated = current.model_copy(update={"status": "generating"})
        self.steps[step_id] = updated
        return updated

    def complete(self, step_id: UUID, *, draft_output) -> AgentStep | None:  # noqa: ANN001
        current = self.steps.get(step_id)
        if current is None or current.status != "generating":
            return None
        updated = current.model_copy(
            update={"status": "pending_review", "draft_output": draft_output}
        )
        self.steps[step_id] = updated
        return updated

    def fail(self, step_id: UUID, *, error: str) -> AgentStep | None:
        current = self.steps.get(step_id)
        if current is None or current.status != "generating":
            return None
        updated = current.model_copy(update={"status": "failed", "error": error})
        self.steps[step_id] = updated
        return updated

    def fail_queued(self, step_id: UUID, *, error: str) -> AgentStep | None:
        current = self.steps.get(step_id)
        if current is None or current.status != "queued":
            return None
        updated = current.model_copy(update={"status": "failed", "error": error})
        self.steps[step_id] = updated
        return updated

    def delete_steps_after(self, run_id: UUID, sequence: int) -> None:
        self.steps = {
            step_id: step
            for step_id, step in self.steps.items()
            if step.run_id != run_id or step.sequence <= sequence
        }

    def cancel_unfinished_steps(self, run_id: UUID, *, reason: str) -> list[AgentStep]:
        cancelled: list[AgentStep] = []
        for step_id, step in list(self.steps.items()):
            if step.run_id == run_id and step.status in {
                "queued",
                "generating",
                "pending_review",
            }:
                updated = step.model_copy(update={"status": "failed", "error": reason})
                self.steps[step_id] = updated
                cancelled.append(updated)
        return cancelled

    def revert_step(self, step_id: UUID) -> AgentStep | None:
        current = self.steps.get(step_id)
        if current is None:
            return None
        updated = current.model_copy(
            update={
                "status": "pending_review",
                "revision": current.revision + 1,
                "final_output": None,
                "error": None,
            }
        )
        self.steps[step_id] = updated
        return updated


class MemoryContent:
    def __init__(self, project: Project, scene: Scene) -> None:
        self.project = project
        self.scene = scene
        self.created_scenes: list[dict] = []
        self.deleted_scene_ids: set[UUID] = set()

    def get_project(self, project_id: UUID) -> Project | None:
        return self.project if project_id == self.project.id else None

    def get_scene(self, scene_id: UUID) -> Scene | None:
        if scene_id in self.deleted_scene_ids:
            return None
        if scene_id == self.scene.id:
            return self.scene
        for created in self.created_scenes:
            if UUID(str(created["id"])) == scene_id:
                return Scene.model_validate(created)
        return None

    def get_project_scenes(self, project_id: UUID) -> list[Scene]:
        scenes: list[Scene] = []
        if self.scene.project_id == project_id and self.scene.id not in self.deleted_scene_ids:
            scenes.append(self.scene)
        scenes.extend(
            Scene.model_validate(created)
            for created in self.created_scenes
            if UUID(str(created["project_id"])) == project_id
            and UUID(str(created["id"])) not in self.deleted_scene_ids
        )
        return sorted(scenes, key=lambda item: item.scene_order)

    def update_project(self, project_id: UUID, **fields):  # noqa: ANN001
        if project_id != self.project.id:
            return None
        self.project = self.project.model_copy(
            update={**fields, "updated_at": datetime.now(UTC)}
        )
        return self.project

    def update_project_if_current(
        self,
        project_id: UUID,
        *,
        expected_updated_at: datetime,
        **fields,
    ):  # noqa: ANN001
        if project_id != self.project.id or self.project.updated_at != expected_updated_at:
            return None
        return self.update_project(project_id, **fields)

    def get_user_settings(self, user_id: UUID):  # noqa: ANN201
        _ = user_id
        return None

    def create_scene(
        self,
        *,
        scene_id: UUID,
        project_id: UUID,
        scene_order: int,
        storyboard_text: str | None,
        voice_script: str | None,
        storyboard_status: str,
    ) -> Scene:
        new_scene = Scene(
            id=scene_id,
            project_id=project_id,
            scene_order=scene_order,
            storyboard_text=storyboard_text,
            voice_script=voice_script,
            storyboard_status=storyboard_status,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.created_scenes.append(new_scene.model_dump(mode="json"))
        return new_scene

    def update_scene(self, scene_id: UUID, **fields):  # noqa: ANN001
        if scene_id == self.scene.id:
            self.scene = self.scene.model_copy(update=fields)
            return self.scene
        # Look in created_scenes
        for s in self.created_scenes:
            if s["id"] == str(scene_id):
                for k, v in fields.items():
                    s[k] = v
                return Scene.model_validate(s)
        return None

    def delete_scene(self, scene_id: UUID) -> None:
        self.deleted_scene_ids.add(scene_id)


class Queue:
    def __init__(self) -> None:
        self.step_ids: list[UUID] = []

    def dispatch_step(self, step_id: UUID) -> str:
        self.step_ids.append(step_id)
        return str(step_id)


def _make_fixtures(hitl_enabled: bool = True):
    now = datetime.now(UTC)
    project = Project(
        id=uuid4(), user_id=uuid4(), title="Derivatives", created_at=now, updated_at=now
    )
    scene = Scene(id=uuid4(), project_id=project.id, scene_order=99, created_at=now, updated_at=now)
    store, queue = MemoryHitlStore(), Queue()
    content = MemoryContent(project, scene)
    service = HitlPipelineService(store=store, content=content, queue=queue)  # type: ignore[arg-type]
    return project, scene, store, queue, content, service


def test_step_sequence_exposes_all_three_generation_stages() -> None:
    assert STEP_SEQUENCE == ("idea_sketcher", "storyboarder", "builder")


@pytest.mark.parametrize("legacy_kind", ["director", "planner", "scene_designer"])
def test_durable_legacy_step_kinds_remain_readable(legacy_kind: str) -> None:
    now = datetime.now(UTC)
    step = AgentStep.model_validate(
        {
            "id": str(uuid4()),
            "run_id": str(uuid4()),
            "project_id": str(uuid4()),
            "scene_id": None,
            "sequence": 1,
            "kind": legacy_kind,
            "status": "approved",
            "input": {},
            "draft_output": None,
            "final_output": None,
            "revision": 1,
            "error": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
    )

    assert step.kind == legacy_kind


def test_auto_pass_kinds_correct() -> None:
    assert AUTO_PASS_KINDS == frozenset({"idea_sketcher"})


def test_storyboarder_creates_scenes_on_approval(monkeypatch) -> None:
    project, scene, store, queue, content, service = _make_fixtures()
    event_order: list[str] = []
    monkeypatch.setattr(
        "app.services.hitl_service.publish_project_event",
        lambda _project_id, event_type, _payload: event_order.append(event_type),
    )
    original_dispatch = queue.dispatch_step

    def dispatch(step_id: UUID) -> str:
        event_order.append("dispatch")
        return original_dispatch(step_id)

    queue.dispatch_step = dispatch  # type: ignore[method-assign]

    run, initial = service.start_project_run(
        project_id=project.id, user_id=project.user_id, prompt="Overall video concept"
    )
    assert initial.kind == "idea_sketcher"
    assert queue.step_ids == [initial.id]
    assert event_order[:2] == ["hitl.step.queued", "dispatch"]

    idea = initial.model_copy(
        update={
            "status": "pending_review",
            "draft_output": {
                "concept": "Derivatives",
                "audience": "Students",
                "learning_goal": "Understand rate of change",
                "key_points": ["Slope", "Instantaneous change"],
                "visual_metaphor": "Moving tangent",
                "scope_notes": "One-variable calculus",
            },
        }
    )
    store.steps[idea.id] = idea
    approved_idea, storyboarder = service.approve(
        run=run, step=idea, expected_revision=1, final_output=None
    )
    assert approved_idea.status == "approved"
    assert storyboarder is not None
    assert storyboarder.kind == "storyboarder"
    assert queue.step_ids == [initial.id, storyboarder.id]

    draft = storyboarder.model_copy(
        update={
            "status": "pending_review",
            "draft_output": {
                "scenes": [
                    {
                        "scene_order": 1,
                        "narration": "Scene 1 narration",
                        "visual_action": "Draw a circle",
                    },
                    {
                        "scene_order": 2,
                        "narration": "Scene 2 narration",
                        "visual_action": "Draw a square",
                    },
                ]
            },
        }
    )
    store.steps[draft.id] = draft

    approved, next_step = service.approve(
        run=run, step=draft, expected_revision=1, final_output=None
    )

    assert approved.status == "approved"
    assert next_step is None
    assert len(content.created_scenes) == 2
    assert content.created_scenes[0]["scene_order"] == 1
    assert content.created_scenes[0]["scene_dsl"] == {"visual_action": "Draw a circle"}
    assert content.created_scenes[1]["scene_order"] == 2
    assert content.created_scenes[1]["scene_dsl"] == {"visual_action": "Draw a square"}

    dispatched_before_reapply = list(queue.step_ids)
    service._apply_approved_output(run, approved)  # noqa: SLF001
    assert len(content.created_scenes) == 2
    assert queue.step_ids == dispatched_before_reapply


def test_storyboard_approval_validates_before_transition(monkeypatch) -> None:
    project, _scene, store, _queue, _content, service = _make_fixtures()
    monkeypatch.setattr(
        "app.services.hitl_service.publish_project_event", lambda *_args, **_kwargs: None
    )
    run, initial = service.start_project_run(
        project_id=project.id, user_id=project.user_id, prompt="Concept"
    )
    idea = initial.model_copy(
        update={
            "status": "pending_review",
            "draft_output": {
                "concept": "Concept",
                "audience": "Students",
                "learning_goal": "Learn the concept",
                "key_points": ["First", "Second"],
                "visual_metaphor": "Diagram",
                "scope_notes": "Introductory",
            },
        }
    )
    store.steps[idea.id] = idea
    _, storyboarder = service.approve(
        run=run, step=idea, expected_revision=1, final_output=None
    )
    assert storyboarder is not None
    pending = storyboarder.model_copy(
        update={"status": "pending_review", "draft_output": {"scenes": []}}
    )
    store.steps[pending.id] = pending

    with pytest.raises(HTTPException) as exc_info:
        service.approve(
            run=run,
            step=pending,
            expected_revision=pending.revision,
            final_output=None,
        )

    assert exc_info.value.status_code == 422
    assert store.steps[pending.id].status == "pending_review"


def test_scene_start_publishes_queued_before_dispatch(monkeypatch) -> None:
    project, scene, _store, queue, _content, service = _make_fixtures()
    order: list[str] = []
    monkeypatch.setattr(
        "app.services.hitl_service.publish_project_event",
        lambda _project_id, event_type, _payload: order.append(event_type),
    )
    original_dispatch = queue.dispatch_step

    def dispatch(step_id: UUID) -> str:
        order.append("dispatch")
        return original_dispatch(step_id)

    queue.dispatch_step = dispatch  # type: ignore[method-assign]
    service.start_scene_run(
        project_id=project.id,
        scene_id=scene.id,
        user_id=project.user_id,
        brief_override=None,
    )
    assert order[:2] == ["hitl.step.queued", "dispatch"]


def test_stale_generating_storyboard_is_failed_instead_of_remaining_active(monkeypatch) -> None:
    project, _scene, store, _queue, _content, service = _make_fixtures()
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "app.services.hitl_service.publish_project_event",
        lambda _project_id, event_type, payload: events.append((event_type, payload)),
    )
    run, step = service.start_project_run(
        project_id=project.id, user_id=project.user_id, prompt="Concept"
    )
    stale = step.model_copy(
        update={"status": "generating", "updated_at": datetime.now(UTC).replace(year=2020)}
    )
    store.steps[stale.id] = stale

    failed = service.expire_stale_generation(run=run, step=stale)

    assert failed.status == "failed"
    assert "worker stopped reporting progress" in (failed.error or "")
    assert store.runs[run.id].status == "failed"
    assert events[-1][0] == "hitl.step.failed"
    assert events[-1][1]["failure_stage"] == "generation_timeout"


def test_stale_queued_storyboard_is_failed_when_no_worker_claims_it(monkeypatch) -> None:
    project, _scene, store, _queue, _content, service = _make_fixtures()
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "app.services.hitl_service.publish_project_event",
        lambda _project_id, event_type, payload: events.append((event_type, payload)),
    )
    run, step = service.start_project_run(
        project_id=project.id, user_id=project.user_id, prompt="Concept"
    )
    stale = step.model_copy(update={"updated_at": datetime.now(UTC).replace(year=2020)})
    store.steps[stale.id] = stale

    failed = service.expire_stale_generation(run=run, step=stale)

    assert failed.status == "failed"
    assert "did not claim" in (failed.error or "")
    assert events[-1][1]["failure_stage"] == "queue_timeout"


def test_stale_revision_does_not_overwrite_human_edit(monkeypatch) -> None:
    project, scene, store, queue, content, service = _make_fixtures()
    monkeypatch.setattr(
        "app.services.hitl_service.publish_project_event", lambda *_args, **_kwargs: None
    )
    run, initial = service.start_scene_run(
        project_id=project.id, scene_id=scene.id, user_id=project.user_id, brief_override=None
    )
    draft = initial.model_copy(
        update={"status": "pending_review", "draft_output": {"manim_code": "code1"}}
    )
    store.steps[draft.id] = draft
    service.edit(run=run, step=draft, expected_revision=1, draft_output={"manim_code": "code2"})

    try:
        service.edit(
            run=run, step=draft, expected_revision=1, draft_output={"manim_code": "code_stale"}
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 409
    else:
        raise AssertionError("Expected stale edit to fail")


def test_auto_approve_and_continue(monkeypatch) -> None:
    """E2E no-HITL path applies the reviewed builder code and completes."""
    project, scene, store, queue, content, service = _make_fixtures()
    monkeypatch.setattr(
        "app.services.hitl_service.publish_project_event", lambda *_args, **_kwargs: None
    )

    run, initial = service.start_scene_run(
        project_id=project.id,
        scene_id=scene.id,
        user_id=project.user_id,
        brief_override=None,
        hitl_enabled=False,
    )
    assert initial.kind == "builder"
    content.project = content.project.model_copy(update={"video_url": "stale-project.mp4"})
    content.scene = content.scene.model_copy(update={"video_url": "stale-scene.mp4"})

    store.steps[initial.id] = initial.model_copy(
        update={
            "status": "pending_review",
            "draft_output": {"manim_code": "from manim import *"},
            "revision": 1,
        }
    )
    completed_step = store.steps[initial.id]

    approved, next_step = service.auto_approve_and_continue(run, completed_step)
    assert approved.status == "approved"
    assert approved.final_output == {"manim_code": "from manim import *"}
    assert next_step is None  # builder is the only step in sequence
    assert content.scene.manim_code == "from manim import *"
    assert content.scene.video_url is None
    assert content.project.video_url is None
    assert content.project.status == "completed"


def test_hitl_on_keeps_builder_pending_until_human_approval(monkeypatch) -> None:
    """E2E HITL path preserves revisioned draft output for a human decision."""
    project, scene, store, _queue, _content, service = _make_fixtures()
    monkeypatch.setattr(
        "app.services.hitl_service.publish_project_event", lambda *_args, **_kwargs: None
    )
    run, builder = service.start_scene_run(
        project_id=project.id,
        scene_id=scene.id,
        user_id=project.user_id,
        brief_override=None,
        hitl_enabled=True,
    )
    pending = builder.model_copy(
        update={"status": "pending_review", "draft_output": {"manim_code": "original"}}
    )
    store.steps[pending.id] = pending
    edited = service.edit(
        run=run, step=pending, expected_revision=1, draft_output={"manim_code": "replacement"}
    )
    assert edited.status == "pending_review"
    assert edited.revision == 2
    assert store.runs[run.id].status == "queued"


def test_hitl_disabled_stores_flag(monkeypatch) -> None:
    """When hitl_enabled=False, the run should store that flag."""
    project, scene, store, queue, content, service = _make_fixtures(hitl_enabled=False)
    monkeypatch.setattr(
        "app.services.hitl_service.publish_project_event", lambda *_args, **_kwargs: None
    )

    run, _ = service.start_scene_run(
        project_id=project.id,
        scene_id=scene.id,
        user_id=project.user_id,
        brief_override=None,
        hitl_enabled=False,
    )
    assert run.hitl_enabled is False


def test_regeneration_immediately_invalidates_scene_and_project_videos(monkeypatch) -> None:
    project, scene, _store, _queue, content, service = _make_fixtures()
    content.scene = scene.model_copy(update={"video_url": "scene-old.mp4"})
    content.project = project.model_copy(update={"video_url": "project-old.mp4"})
    monkeypatch.setattr(
        "app.services.hitl_service.publish_project_event", lambda *_args, **_kwargs: None
    )

    service.start_scene_run(
        project_id=project.id,
        scene_id=scene.id,
        user_id=project.user_id,
        brief_override=None,
    )

    assert content.scene.generation_status == "generating"
    assert content.scene.video_url is None
    assert content.project.video_url is None
    assert content.project.status == "processing"


def test_new_builder_run_cancels_previous_active_run(monkeypatch) -> None:
    project, scene, store, _queue, _content, service = _make_fixtures()
    monkeypatch.setattr(
        "app.services.hitl_service.publish_project_event", lambda *_args, **_kwargs: None
    )

    old_run, old_step = service.start_scene_run(
        project_id=project.id,
        scene_id=scene.id,
        user_id=project.user_id,
        brief_override=None,
    )
    new_run, new_step = service.start_scene_run(
        project_id=project.id,
        scene_id=scene.id,
        user_id=project.user_id,
        brief_override="A different approach",
    )

    assert store.runs[old_run.id].status == "cancelled"
    assert store.steps[old_step.id].status == "failed"
    assert store.steps[old_step.id].error == "Cancelled because a newer Builder run was started"
    assert store.runs[new_run.id].status == "queued"
    assert store.steps[new_step.id].status == "queued"


def test_superseded_builder_cannot_apply_late_approval(monkeypatch) -> None:
    project, scene, store, _queue, content, service = _make_fixtures()
    monkeypatch.setattr(
        "app.services.hitl_service.publish_project_event", lambda *_args, **_kwargs: None
    )
    old_run, old_step = service.start_scene_run(
        project_id=project.id,
        scene_id=scene.id,
        user_id=project.user_id,
        brief_override=None,
    )
    old_pending = old_step.model_copy(
        update={
            "status": "pending_review",
            "draft_output": {"manim_code": "old late code"},
        }
    )
    store.steps[old_step.id] = old_pending

    new_run, _new_step = service.start_scene_run(
        project_id=project.id,
        scene_id=scene.id,
        user_id=project.user_id,
        brief_override="New owner",
    )

    with pytest.raises(HTTPException) as exc_info:
        service.approve(
            run=old_run,
            step=old_pending,
            expected_revision=old_pending.revision,
            final_output=None,
        )

    assert exc_info.value.status_code == 409
    assert store.runs[old_run.id].status == "cancelled"
    assert store.runs[new_run.id].status == "queued"
    assert content.scene.manim_code != "old late code"
    assert content.scene.generation_status == "generating"


def test_new_master_run_cancels_previous_active_master(monkeypatch) -> None:
    project, _scene, store, _queue, _content, service = _make_fixtures()
    monkeypatch.setattr(
        "app.services.hitl_service.publish_project_event", lambda *_args, **_kwargs: None
    )

    old_run, old_step = service.start_project_run(
        project_id=project.id,
        user_id=project.user_id,
        prompt="Old storyboard",
    )
    new_run, new_step = service.start_project_run(
        project_id=project.id,
        user_id=project.user_id,
        prompt="Replacement storyboard",
    )

    assert store.runs[old_run.id].status == "cancelled"
    assert store.steps[old_step.id].status == "failed"
    assert store.runs[new_run.id].status == "queued"
    assert store.steps[new_step.id].status == "queued"


def test_builder_rollback_invalidates_approved_code_and_video(monkeypatch) -> None:
    project, scene, store, _queue, content, service = _make_fixtures()
    monkeypatch.setattr(
        "app.services.hitl_service.publish_project_event", lambda *_args, **_kwargs: None
    )
    run, builder = service.start_scene_run(
        project_id=project.id,
        scene_id=scene.id,
        user_id=project.user_id,
        brief_override=None,
    )
    pending = builder.model_copy(
        update={
            "status": "pending_review",
            "draft_output": {"manim_code": "from manim import *"},
        }
    )
    store.steps[pending.id] = pending
    approved, _ = service.approve(
        run=run,
        step=pending,
        expected_revision=pending.revision,
        final_output=None,
    )
    content.scene = content.scene.model_copy(update={"video_url": "scene.mp4"})
    content.project = content.project.model_copy(update={"video_url": "project.mp4"})

    rolled_back, reverted = service.rollback(run=run, target_step_id=approved.id)

    assert rolled_back.status == "waiting_for_human"
    assert reverted.status == "pending_review"
    assert content.scene.manim_code is None
    assert content.scene.video_url is None
    assert content.scene.generation_status == "pending"
    assert content.project.video_url is None
    assert content.project.status == "processing"


def test_storyboard_rollback_cancels_children_and_removes_derived_scenes(monkeypatch) -> None:
    project, _scene, store, _queue, content, service = _make_fixtures()
    monkeypatch.setattr(
        "app.services.hitl_service.publish_project_event", lambda *_args, **_kwargs: None
    )
    run, idea = service.start_project_run(
        project_id=project.id,
        user_id=project.user_id,
        prompt="Two scenes",
    )
    pending_idea = idea.model_copy(
        update={
            "status": "pending_review",
            "draft_output": {
                "concept": "Shapes",
                "audience": "Students",
                "learning_goal": "Compare shapes",
                "key_points": ["Circle", "Square"],
                "visual_metaphor": "Geometry canvas",
                "scope_notes": "Basic geometry",
            },
        }
    )
    store.steps[pending_idea.id] = pending_idea
    _, storyboard = service.approve(
        run=run,
        step=pending_idea,
        expected_revision=pending_idea.revision,
        final_output=None,
    )
    assert storyboard is not None
    pending = storyboard.model_copy(
        update={
            "status": "pending_review",
            "draft_output": {
                "scenes": [
                    {
                        "scene_order": 1,
                        "narration": "First",
                        "visual_action": "Draw a circle",
                    },
                    {
                        "scene_order": 2,
                        "narration": "Second",
                        "visual_action": "Draw a square",
                    },
                ]
            },
        }
    )
    store.steps[pending.id] = pending
    approved, _ = service.approve(
        run=run,
        step=pending,
        expected_revision=pending.revision,
        final_output=None,
    )
    child_runs = [candidate for candidate in store.runs.values() if candidate.scene_id]
    assert len(child_runs) == 2

    rolled_back, reverted = service.rollback(run=run, target_step_id=approved.id)

    assert rolled_back.status == "waiting_for_human"
    assert reverted.status == "pending_review"
    assert content.get_project_scenes(project.id) == []
    assert content.project.status == "draft"
    assert all(store.runs[child.id].status == "cancelled" for child in child_runs)
    child_steps = [step for step in store.steps.values() if step.run_id in {r.id for r in child_runs}]
    assert child_steps and all(step.status == "failed" for step in child_steps)


def test_storyboard_continuations_are_folded_before_builder_runs() -> None:
    normalized = normalize_storyboard_output(
        {
            "scenes": [
                {
                    "scene_order": 1,
                    "continuity": "new_section",
                    "narration": "Draw the number line.",
                    "visual_action": "Create a number line.",
                },
                {
                    "scene_order": 2,
                    "continuity": "continue_animation",
                    "narration": "Move the marker right.",
                    "visual_action": "Animate the existing marker to 3.",
                },
                {
                    "scene_order": 3,
                    "continuity": "new_section",
                    "narration": "Now show the equation.",
                    "visual_action": "Create a fresh equation layout.",
                },
            ]
        }
    )

    scenes = normalized["scenes"]
    assert len(scenes) == 2
    assert [scene["scene_order"] for scene in scenes] == [1, 2]
    assert "Move the marker right." in scenes[0]["narration"]
    assert "do not rebuild them" in scenes[0]["visual_action"]
