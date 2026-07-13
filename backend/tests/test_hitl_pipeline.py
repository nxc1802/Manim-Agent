from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.services.hitl_service import AUTO_PASS_KINDS, HitlPipelineService, STEP_SEQUENCE
from shared.schemas.hitl import AgentStep, AiRun
from shared.schemas.project import Project
from shared.schemas.scene import Scene


class MemoryHitlStore:
    def __init__(self) -> None:
        self.runs: dict[UUID, AiRun] = {}
        self.steps: dict[UUID, AgentStep] = {}

    def create_run(self, *, project_id: UUID, scene_id: UUID, user_id: UUID, hitl_enabled: bool = True) -> AiRun:
        now = datetime.now(UTC)
        run = AiRun(id=uuid4(), project_id=project_id, scene_id=scene_id, user_id=user_id, status="queued", hitl_enabled=hitl_enabled, created_at=now, updated_at=now)
        self.runs[run.id] = run
        return run

    def get_run(self, run_id: UUID) -> AiRun | None:
        return self.runs.get(run_id)

    def create_step(self, *, run: AiRun, sequence: int, kind, input_data):  # noqa: ANN001
        now = datetime.now(UTC)
        step = AgentStep(id=uuid4(), run_id=run.id, project_id=run.project_id, scene_id=run.scene_id, sequence=sequence, kind=kind, status="queued", input=input_data, revision=1, created_at=now, updated_at=now)
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
        updated = current.model_copy(update={"draft_output": draft_output, "revision": expected_revision + 1})
        self.steps[step.id] = updated
        return updated

    def approve(self, step: AgentStep, *, final_output, expected_revision: int):  # noqa: ANN001
        current = self.steps[step.id]
        if current.status != "pending_review" or current.revision != expected_revision:
            return None
        updated = current.model_copy(update={"status": "approved", "final_output": final_output, "revision": expected_revision + 1})
        self.steps[step.id] = updated
        return updated

    def reject(self, step: AgentStep, *, feedback: str, expected_revision: int):  # noqa: ANN001
        current = self.steps[step.id]
        if current.status != "pending_review" or current.revision != expected_revision:
            return None
        updated = current.model_copy(update={"status": "rejected", "error": feedback, "revision": expected_revision + 1})
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
        updated = current.model_copy(update={"status": "pending_review", "draft_output": draft_output})
        self.steps[step_id] = updated
        return updated


class MemoryContent:
    def __init__(self, project: Project, scene: Scene) -> None:
        self.project = project
        self.scene = scene

    def get_project(self, project_id: UUID) -> Project | None:
        return self.project if project_id == self.project.id else None

    def get_scene(self, scene_id: UUID) -> Scene | None:
        return self.scene if scene_id == self.scene.id else None

    def update_scene(self, scene_id: UUID, **fields):  # noqa: ANN001
        if scene_id != self.scene.id:
            return None
        self.scene = self.scene.model_copy(update=fields)
        return self.scene


class Queue:
    def __init__(self) -> None:
        self.step_ids: list[UUID] = []

    def dispatch_step(self, step_id: UUID) -> str:
        self.step_ids.append(step_id)
        return str(step_id)


def _make_fixtures(hitl_enabled: bool = True):
    now = datetime.now(UTC)
    project = Project(id=uuid4(), user_id=uuid4(), title="Derivatives", created_at=now, updated_at=now)
    scene = Scene(id=uuid4(), project_id=project.id, scene_order=0, created_at=now, updated_at=now)
    store, queue = MemoryHitlStore(), Queue()
    content = MemoryContent(project, scene)
    service = HitlPipelineService(store=store, content=content, queue=queue)  # type: ignore[arg-type]
    return project, scene, store, queue, content, service


def test_step_sequence_includes_visual_reviewer() -> None:
    assert "visual_reviewer" in STEP_SEQUENCE
    assert STEP_SEQUENCE[-1] == "visual_reviewer"


def test_auto_pass_kinds_correct() -> None:
    assert "builder" in AUTO_PASS_KINDS
    assert "code_reviewer" in AUTO_PASS_KINDS
    assert "visual_reviewer" in AUTO_PASS_KINDS
    assert "director" not in AUTO_PASS_KINDS
    assert "planner" not in AUTO_PASS_KINDS


def test_each_approved_step_queues_exactly_one_next_step(monkeypatch) -> None:
    project, scene, store, queue, content, service = _make_fixtures()
    monkeypatch.setattr("app.services.hitl_service.publish_project_event", lambda *_args, **_kwargs: None)

    run, initial = service.start(project_id=project.id, scene_id=scene.id, user_id=project.user_id, brief_override=None)
    assert initial.kind == "director"
    assert queue.step_ids == [initial.id]

    draft = initial.model_copy(update={"status": "pending_review", "draft_output": {"storyboard": "draft"}})
    store.steps[draft.id] = draft
    edited = service.edit(run=run, step=draft, expected_revision=1, draft_output={"storyboard": "human edit"})
    approved, next_step = service.approve(run=run, step=edited, expected_revision=2, final_output=None)

    assert approved.final_output == {"storyboard": "human edit"}
    assert next_step is not None and next_step.kind == "planner"
    assert queue.step_ids == [initial.id, next_step.id]


def test_stale_revision_does_not_overwrite_human_edit(monkeypatch) -> None:
    project, scene, store, queue, content, service = _make_fixtures()
    monkeypatch.setattr("app.services.hitl_service.publish_project_event", lambda *_args, **_kwargs: None)
    run, initial = service.start(project_id=project.id, scene_id=scene.id, user_id=project.user_id, brief_override=None)
    draft = initial.model_copy(update={"status": "pending_review", "draft_output": {"storyboard": "first"}})
    store.steps[draft.id] = draft
    service.edit(run=run, step=draft, expected_revision=1, draft_output={"storyboard": "newer"})

    try:
        service.edit(run=run, step=draft, expected_revision=1, draft_output={"storyboard": "stale"})
    except Exception as exc:  # FastAPI HTTPException is enough evidence at service level.
        assert getattr(exc, "status_code", None) == 409
    else:
        raise AssertionError("Expected stale edit to fail")


def test_auto_approve_and_continue(monkeypatch) -> None:
    """When a step is auto-approved, the service should approve and queue next."""
    project, scene, store, queue, content, service = _make_fixtures()
    monkeypatch.setattr("app.services.hitl_service.publish_project_event", lambda *_args, **_kwargs: None)

    run, initial = service.start(project_id=project.id, scene_id=scene.id, user_id=project.user_id, brief_override=None)

    # Simulate worker completing the step
    store.steps[initial.id] = initial.model_copy(update={"status": "pending_review", "draft_output": {"storyboard": "ai output"}, "revision": 1})
    completed_step = store.steps[initial.id]

    approved, next_step = service.auto_approve_and_continue(run, completed_step)
    assert approved.status == "approved"
    assert approved.final_output == {"storyboard": "ai output"}
    assert next_step is not None
    assert next_step.kind == "planner"


def test_hitl_disabled_stores_flag(monkeypatch) -> None:
    """When hitl_enabled=False, the run should store that flag."""
    project, scene, store, queue, content, service = _make_fixtures(hitl_enabled=False)
    monkeypatch.setattr("app.services.hitl_service.publish_project_event", lambda *_args, **_kwargs: None)

    run, _ = service.start(project_id=project.id, scene_id=scene.id, user_id=project.user_id, brief_override=None, hitl_enabled=False)
    assert run.hitl_enabled is False


def test_builder_output_injects_manim_code_for_code_reviewer(monkeypatch) -> None:
    """When builder is approved, the next step (code_reviewer) should get manim_code in input."""
    project, scene, store, queue, content, service = _make_fixtures()
    monkeypatch.setattr("app.services.hitl_service.publish_project_event", lambda *_args, **_kwargs: None)

    run, _ = service.start(project_id=project.id, scene_id=scene.id, user_id=project.user_id, brief_override=None)

    # Simulate approved builder step
    builder_step = store.create_step(run=run, sequence=4, kind="builder", input_data={})
    store.steps[builder_step.id] = builder_step.model_copy(update={
        "status": "pending_review",
        "draft_output": {"manim_code": "from manim import *"},
        "revision": 1,
    })
    pending_builder = store.steps[builder_step.id]
    approved, next_step = service.auto_approve_and_continue(run, pending_builder)

    assert next_step is not None
    assert next_step.kind == "code_reviewer"
    assert next_step.input.get("manim_code") == "from manim import *"


def test_full_pipeline_six_steps(monkeypatch) -> None:
    """The full pipeline should have exactly 6 step kinds."""
    assert len(STEP_SEQUENCE) == 6
    assert STEP_SEQUENCE == ("director", "planner", "scene_designer", "builder", "code_reviewer", "visual_reviewer")


def test_code_reviewer_output_applies_to_scene(monkeypatch) -> None:
    """When code_reviewer is approved, the manim_code should be saved to scene."""
    project, scene, store, queue, content, service = _make_fixtures()
    monkeypatch.setattr("app.services.hitl_service.publish_project_event", lambda *_args, **_kwargs: None)

    run, _ = service.start(project_id=project.id, scene_id=scene.id, user_id=project.user_id, brief_override=None)

    # Simulate code_reviewer step that fixed the code
    reviewer_step = store.create_step(run=run, sequence=5, kind="code_reviewer", input_data={"manim_code": "original"})
    store.steps[reviewer_step.id] = reviewer_step.model_copy(update={
        "status": "pending_review",
        "draft_output": {"passed": True, "manim_code": "fixed_code", "iterations": [], "total_attempts": 1},
        "revision": 1,
    })
    pending = store.steps[reviewer_step.id]
    approved, next_step = service.auto_approve_and_continue(run, pending)

    assert content.scene.manim_code == "fixed_code"
    assert next_step is not None
    assert next_step.kind == "visual_reviewer"
