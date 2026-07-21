from __future__ import annotations

import asyncio
import importlib
import json
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.api.v1.internal import (
    _auto_approval_failure,
    _render_worker_input_url,
    claim_render_job,
    complete_render_job,
    complete_step,
    fail_render_job,
)
from app.api.v1.render import (
    _idempotency_scope,
    enqueue_render,
    get_persisted_render_url,
    list_project_render_jobs,
)
from app.core.config import settings
from app.core.websocket_manager import ConnectionManager
from app.db.content_store import RedisContentStore
from app.db.supabase_store import SupabaseContentStore
from app.main import app
from app.services.ai_queue import AiQueue, AiQueueUnavailable
from app.services.cache import CACHE_MISS, RedisJsonCache
from app.services.events import publish_project_event, step_event_payload
from app.services.hitl_store import SupabaseHitlStore
from app.services.job_store import RedisRenderJobStore
from app.services.render_snapshot import project_render_source, scene_render_source
from fakeredis import FakeRedis
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from kombu.exceptions import OperationalError as KombuOperationalError
from redis.exceptions import RedisError
from shared.schemas.hitl import AgentStep, AiRun, InternalStepCompleteRequest
from shared.schemas.project import Project
from shared.schemas.render_api import RenderEnqueueBody
from shared.schemas.scene import Scene
from shared.schemas.user import UserSettings


def _redis() -> FakeRedis:
    return FakeRedis(decode_responses=True)


def _project_row(project_id: UUID, user_id: UUID, *, title: str = "Cache test") -> dict[str, Any]:
    now = datetime.now(tz=UTC).isoformat()
    return {
        "id": str(project_id),
        "user_id": str(user_id),
        "title": title,
        "description": None,
        "source_language": "en",
        "target_scenes": None,
        "config": {},
        "status": "draft",
        "video_url": None,
        "created_at": now,
        "updated_at": now,
    }


def test_project_contract_round_trips_non_null_video_url() -> None:
    row = _project_row(uuid4(), uuid4())
    row["video_url"] = "supabase://videos/project/final.mp4"

    project = Project.model_validate(row)

    assert project.video_url == row["video_url"]
    assert project.model_dump(mode="json")["video_url"] == row["video_url"]


def test_redis_development_store_has_settings_and_full_project_parity() -> None:
    redis = _redis()
    store = RedisContentStore(redis)
    user_id, project_id = uuid4(), uuid4()
    store.create_project(
        project_id=project_id,
        user_id=user_id,
        title="Project",
        description=None,
        source_language="en",
        target_scenes=2,
        status="draft",
        config={},
    )
    for order in (2, 1):
        store.create_scene(
            scene_id=uuid4(),
            project_id=project_id,
            scene_order=order,
            storyboard_text=None,
            voice_script=None,
            storyboard_status="approved",
        )

    saved = store.upsert_user_settings(UserSettings(user_id=user_id, theme="light"))
    assert store.get_user_settings(user_id) == saved
    assert [scene.scene_order for scene in store.get_project_scenes(project_id)] == [1, 2]


def test_supabase_content_reads_are_cached_and_writes_invalidate_lists(monkeypatch) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-key")
    cache = RedisJsonCache(_redis())
    store = SupabaseContentStore(cache=cache)
    project_id, user_id = uuid4(), uuid4()
    row = _project_row(project_id, user_id)
    calls: list[tuple[str, str, dict[str, str] | None]] = []

    def request(
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        body: Any = None,
    ) -> list[dict[str, Any]]:
        calls.append((method, table, params))
        if method == "PATCH":
            row.update(body or {})
            row["updated_at"] = datetime.now(tz=UTC).isoformat()
            return [dict(row)]
        if params and params.get("select") == "id":
            return [{"id": str(project_id)}]
        return [dict(row)]

    monkeypatch.setattr(store, "_request", request)

    assert store.get_project(project_id) is not None
    assert store.get_project(project_id) is not None
    assert len(calls) == 1

    first, total = store.list_projects_for_user(user_id, limit=20, offset=0)
    assert first[0].title == "Cache test" and total == 1
    assert len(calls) == 3
    store.list_projects_for_user(user_id, limit=20, offset=0)
    assert len(calls) == 3

    store.update_project(project_id, title="Updated")
    assert store.get_project(project_id).title == "Updated"  # type: ignore[union-attr]
    store.list_projects_for_user(user_id, limit=20, offset=0)
    assert len(calls) == 6  # PATCH plus refreshed data/count after generation bump

    current = store.get_project(project_id)
    assert current is not None
    store.update_project_if_current(
        project_id,
        expected_updated_at=current.updated_at,
        title="CAS update",
    )
    method, table, params = calls[-1]
    assert (method, table) == ("PATCH", "projects")
    assert params == {
        "id": f"eq.{project_id}",
        "updated_at": f"eq.{current.updated_at.isoformat()}",
    }


def test_supabase_settings_use_atomic_table_upsert_without_auth_metadata(monkeypatch) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-key")
    store = SupabaseContentStore(cache=RedisJsonCache(_redis()))
    user_id = uuid4()
    table_row: dict[str, Any] = {}
    calls: list[tuple[str, dict[str, str] | None, str | None]] = []

    def request(
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        body: Any = None,
        prefer: str | None = None,
    ) -> list[dict[str, Any]]:
        assert table == "user_settings"
        calls.append((method, params, prefer))
        table_row.update(body or {})
        return [dict(table_row)]

    monkeypatch.setattr(store, "_request", request)
    requested = UserSettings(
        user_id=user_id,
        llm_agent_configs={
            "idea_sketcher": {"reasoning_effort": "high"},
            "code_reviewer": {
                "review_tiers": [
                    {
                        "model": "gemini-3-flash-preview",
                        "max_attempts": 2,
                        "reasoning_effort": "medium",
                    }
                ]
            },
        },
        tts_enabled=True,
    )

    saved = store.upsert_user_settings(requested)

    assert saved == requested
    assert table_row["llm_agent_configs"]["idea_sketcher"]["reasoning_effort"] == "high"
    assert table_row["theme"] == "dark"
    assert calls == [
        (
            "POST",
            {"on_conflict": "user_id"},
            "resolution=merge-duplicates,return=representation",
        )
    ]


def test_hitl_reads_are_cached_and_transitions_invalidate_step_list(monkeypatch) -> None:
    redis = _redis()
    store = SupabaseHitlStore(
        "https://example.supabase.co", "service-key", cache=RedisJsonCache(redis)
    )
    now = datetime.now(tz=UTC).isoformat()
    run_id, project_id, scene_id, user_id, step_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    run_row = {
        "id": str(run_id),
        "project_id": str(project_id),
        "scene_id": str(scene_id),
        "user_id": str(user_id),
        "status": "queued",
        "hitl_enabled": True,
        "created_at": now,
        "updated_at": now,
    }
    step_row = {
        "id": str(step_id),
        "run_id": str(run_id),
        "project_id": str(project_id),
        "scene_id": str(scene_id),
        "sequence": 1,
        "kind": "builder",
        "status": "queued",
        "input": {},
        "draft_output": None,
        "final_output": None,
        "revision": 1,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    calls = 0

    def request(
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        nonlocal calls
        calls += 1
        if table == "ai_runs":
            return [dict(run_row)]
        if method == "PATCH":
            step_row.update(body or {})
        return [dict(step_row)]

    monkeypatch.setattr(store, "_request", request)
    assert store.get_run(run_id) is not None
    assert store.get_run(run_id) is not None
    assert calls == 1
    assert store.list_steps(run_id)[0].status == "queued"
    store.list_steps(run_id)
    assert calls == 2
    assert store.claim(step_id).status == "generating"  # type: ignore[union-attr]
    assert store.list_steps(run_id)[0].status == "generating"
    assert calls == 4


def test_dashboard_uses_actual_redis_render_jobs() -> None:
    redis = _redis()
    content = RedisContentStore(redis)
    jobs = RedisRenderJobStore(redis)
    user_id, project_id, scene_id, job_id = uuid4(), uuid4(), uuid4(), uuid4()
    content.create_project(
        project_id=project_id,
        user_id=user_id,
        title="Stats",
        description=None,
        source_language="en",
        target_scenes=1,
        status="draft",
        config={},
    )
    jobs.create_queued_job(
        job_id=job_id,
        project_id=project_id,
        scene_id=scene_id,
        job_type="full",
        render_quality="720p",
        docker_image_tag=None,
    )
    assert content.get_dashboard_stats(user_id).active_jobs == 1
    started = datetime.now(tz=UTC)
    assert jobs.transition(
        job_id, expected_status="queued", status="rendering", started_at=started
    )
    assert jobs.transition(
        job_id,
        expected_status="rendering",
        status="completed",
        completed_at=started + timedelta(hours=1),
    )
    stats = content.get_dashboard_stats(user_id)
    assert stats.active_jobs == 0
    assert stats.total_render_time_hours == 1.0


def test_legacy_render_job_cache_is_migrated_during_index_backfill() -> None:
    redis = _redis()
    jobs = RedisRenderJobStore(redis)
    project_id, scene_id, job_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(tz=UTC).isoformat()
    redis.set(
        f"{settings.redis_prefix}:render_job:{job_id}",
        json.dumps(
            {
                "id": str(job_id),
                "project_id": str(project_id),
                "scene_id": str(scene_id),
                "job_type": "full",
                "render_quality": "720p",
                "status": "queued",
                "progress": 0,
                "webhook_url": None,
                "created_at": now,
            }
        ),
    )

    assert jobs.aggregate_for_projects({project_id}) == (1, 0.0)
    canonical = json.loads(redis.get(f"{settings.redis_prefix}:render_job:{job_id}"))
    assert "webhook_url" not in canonical


def test_full_project_claim_returns_all_ordered_scene_sources(monkeypatch) -> None:
    redis = _redis()
    content = RedisContentStore(redis)
    jobs = RedisRenderJobStore(redis)
    user_id, project_id = uuid4(), uuid4()
    content.create_project(
        project_id=project_id,
        user_id=user_id,
        title="Full project",
        description=None,
        source_language="en",
        target_scenes=2,
        status="completed",
        config={},
    )
    for order in (1, 2):
        scene = content.create_scene(
            scene_id=uuid4(),
            project_id=project_id,
            scene_order=order,
            storyboard_text=None,
            voice_script=None,
            storyboard_status="approved",
        )
        content.update_scene(
            scene.id,
            manim_code=f"CODE_{order}",
            generation_status="completed",
            video_url=f"file:///artifacts/scene-{order}.mp4",
        )
    job = jobs.create_queued_job(
        job_id=uuid4(),
        project_id=project_id,
        scene_id=None,
        job_type="full_project",
        render_quality="720p",
        docker_image_tag=None,
    )
    monkeypatch.setattr("app.api.v1.internal.publish_project_event", lambda *_args: True)
    payload = claim_render_job(job.id, jobs=jobs, content=content)
    assert payload["job_type"] == "full_project"
    assert [scene["manim_code"] for scene in payload["scenes"]] == ["CODE_1", "CODE_2"]
    assert [scene["scene_order"] for scene in payload["scenes"]] == [1, 2]
    assert [scene["voice_script"] for scene in payload["scenes"]] == [None, None]
    assert payload["source_language"] == "en"
    assert payload["settings"]["video_quality"] == "720p"
    assert payload["metadata"]["source_snapshot"]["kind"] == "full_project"


def test_worker_can_fail_render_that_errors_before_claim(monkeypatch) -> None:
    redis = _redis()
    jobs = RedisRenderJobStore(redis)
    job = jobs.create_queued_job(
        job_id=uuid4(),
        project_id=uuid4(),
        scene_id=uuid4(),
        job_type="full",
        render_quality="720p",
        docker_image_tag=None,
    )
    monkeypatch.setattr("app.api.v1.internal.publish_project_event", lambda *_args: True)
    result = fail_render_job(job.id, {"error": "claim validation failed"}, jobs=jobs)
    assert result["status"] == "failed"
    assert jobs.get(job.id).status == "failed"  # type: ignore[union-attr]


def test_render_idempotency_is_scoped_to_caller_project_and_request() -> None:
    key = "client-retry-key"
    user_id, project_id = uuid4(), uuid4()
    body = RenderEnqueueBody(render_type="full", scene_id=uuid4(), quality="720p")
    baseline = _idempotency_scope(
        key, user_id=user_id, project_id=project_id, body=body
    )
    assert baseline != _idempotency_scope(
        key, user_id=uuid4(), project_id=project_id, body=body
    )
    assert baseline != _idempotency_scope(
        key, user_id=user_id, project_id=uuid4(), body=body
    )
    assert baseline != _idempotency_scope(
        key,
        user_id=user_id,
        project_id=project_id,
        body=body.model_copy(update={"quality": "1080p"}),
    )
    assert baseline != _idempotency_scope(
        key,
        user_id=user_id,
        project_id=project_id,
        body=body,
        source_fingerprint="new-source-revision",
    )


def test_ai_queue_normalizes_broker_errors() -> None:
    class BrokenCelery:
        def send_task(self, *_args: Any, **_kwargs: Any) -> None:
            raise KombuOperationalError("broker down")

    queue = AiQueue(celery_app=BrokenCelery())  # type: ignore[arg-type]
    with pytest.raises(AiQueueUnavailable, match="queue is unavailable"):
        queue.dispatch_render(uuid4())


def test_active_render_reservation_and_reload_listing_are_deduplicated(monkeypatch) -> None:
    redis = _redis()
    content = RedisContentStore(redis)
    jobs = RedisRenderJobStore(redis)
    user_id, project_id, scene_id = settings.dev_default_user_id, uuid4(), uuid4()
    content.create_project(
        project_id=project_id,
        user_id=user_id,
        title="Render",
        description=None,
        source_language="en",
        target_scenes=1,
        status="draft",
        config={},
    )
    content.create_scene(
        scene_id=scene_id,
        project_id=project_id,
        scene_order=1,
        storyboard_text="Scene",
        voice_script="Scene",
        storyboard_status="approved",
    )
    content.update_scene(
        scene_id,
        manim_code="from manim import *",
        generation_status="completed",
    )

    order: list[str] = []

    class Queue:
        def dispatch_render(self, job_id: UUID) -> str:
            order.append(f"dispatch:{job_id}")
            return "task-id"

    monkeypatch.setattr("app.api.v1.render.AiQueue", lambda: Queue())
    monkeypatch.setattr(
        "app.api.v1.render.publish_project_event",
        lambda _project_id, event_type, _payload: order.append(event_type) or True,
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": f"/v1/projects/{project_id}/render",
            "root_path": "",
            "scheme": "http",
            "query_string": b"",
            "headers": [],
            "client": ("test", 123),
            "server": ("testserver", 80),
            "app": app,
        }
    )
    body = RenderEnqueueBody(render_type="full", scene_id=scene_id, quality="720p")
    first = enqueue_render(
        project_id=project_id,
        body=body,
        request=request,
        user_id=user_id,
        content=content,
        store=jobs,
        x_idempotency_key=None,
    )
    first_id = UUID(json.loads(first.body)["job_id"])
    assert first.status_code == 202
    assert order == ["render.queued", f"dispatch:{first_id}"]

    second = enqueue_render(
        project_id=project_id,
        body=body,
        request=request,
        user_id=user_id,
        content=content,
        store=jobs,
        x_idempotency_key=None,
    )
    assert second.status_code == 200
    assert UUID(json.loads(second.body)["job_id"]) == first_id
    active = list_project_render_jobs(
        project_id=project_id,
        active=True,
        user_id=user_id,
        content=content,
        store=jobs,
    )
    assert [job.id for job in active] == [first_id]

    assert jobs.transition(first_id, expected_status="queued", status="failed")
    client_key = "retry-the-same-source"
    current_scene = content.get_scene(scene_id)
    assert current_scene is not None
    scope = _idempotency_scope(
        client_key,
        user_id=user_id,
        project_id=project_id,
        body=body,
        source_fingerprint=str(scene_render_source(current_scene)["source_fingerprint"]),
    )
    jobs.set_idempotent_job_id(scope, first_id)
    retry = enqueue_render(
        project_id=project_id,
        body=body,
        request=request,
        user_id=user_id,
        content=content,
        store=jobs,
        x_idempotency_key=client_key,
    )
    replacement_id = UUID(json.loads(retry.body)["job_id"])
    assert retry.status_code == 202
    assert replacement_id != first_id
    assert jobs.get_idempotent_job_id(scope) == replacement_id


def test_persisted_video_signing_does_not_depend_on_render_job_cache(monkeypatch) -> None:
    redis = _redis()
    content = RedisContentStore(redis)
    user_id, project_id, scene_id = settings.dev_default_user_id, uuid4(), uuid4()
    content.create_project(
        project_id=project_id,
        user_id=user_id,
        title="Persisted video",
        description=None,
        source_language="en",
        target_scenes=1,
        status="completed",
        config={},
    )
    content.create_scene(
        scene_id=scene_id,
        project_id=project_id,
        scene_order=1,
        storyboard_text=None,
        voice_script=None,
        storyboard_status="approved",
    )
    object_path = f"{project_id}/renders/{uuid4()}.mp4"
    content.update_scene(scene_id, video_url=f"supabase://videos/{object_path}")
    monkeypatch.setattr(settings, "supabase_storage_bucket", "videos")
    monkeypatch.setattr(
        "app.api.v1.render.sign_storage_object_read_url",
        lambda *, object_path: f"https://signed.example/{object_path}",
    )

    response = get_persisted_render_url(
        project_id=project_id,
        scene_id=scene_id,
        user_id=user_id,
        content=content,
    )
    assert str(response.signed_url) == f"https://signed.example/{object_path}"


def test_scene_render_completion_invalidates_stale_project_video(monkeypatch) -> None:
    redis = _redis()
    content = RedisContentStore(redis)
    jobs = RedisRenderJobStore(redis)
    user_id, project_id, scene_id, job_id = uuid4(), uuid4(), uuid4(), uuid4()
    content.create_project(
        project_id=project_id,
        user_id=user_id,
        title="Lifecycle",
        description=None,
        source_language="en",
        target_scenes=1,
        status="completed",
        config={},
    )
    content.update_project(project_id, video_url="supabase://videos/stale-project.mp4")
    content.create_scene(
        scene_id=scene_id,
        project_id=project_id,
        scene_order=1,
        storyboard_text=None,
        voice_script=None,
        storyboard_status="approved",
    )
    scene = content.update_scene(
        scene_id,
        manim_code="from manim import *",
        generation_status="completed",
    )
    assert scene is not None
    jobs.create_queued_job(
        job_id=job_id,
        project_id=project_id,
        scene_id=scene_id,
        job_type="full",
        render_quality="720p",
        docker_image_tag=None,
        metadata=scene_render_source(scene),
    )
    assert jobs.transition(job_id, expected_status="queued", status="rendering")
    monkeypatch.setattr(settings, "supabase_storage_bucket", "videos")
    monkeypatch.setattr("app.api.v1.internal.publish_project_event", lambda *_args: True)
    asset_url = f"supabase://videos/{project_id}/renders/{job_id}.mp4"

    complete_render_job(
        job_id,
        {"asset_url": asset_url},
        jobs=jobs,
        content=content,
    )
    assert content.get_scene(scene_id).video_url == asset_url  # type: ignore[union-attr]
    assert content.get_project(project_id).video_url is None  # type: ignore[union-attr]

    # A worker retry after the terminal transition must not invalidate a newer
    # full-project artifact.
    content.update_project(project_id, video_url="supabase://videos/current-project.mp4")
    duplicate = complete_render_job(
        job_id,
        {"asset_url": asset_url},
        jobs=jobs,
        content=content,
    )
    assert duplicate["status"] == "completed"
    assert content.get_project(project_id).video_url == "supabase://videos/current-project.mp4"  # type: ignore[union-attr]


def test_stale_scene_render_is_failed_without_reintroducing_video(monkeypatch) -> None:
    redis = _redis()
    content = RedisContentStore(redis)
    jobs = RedisRenderJobStore(redis)
    user_id, project_id, scene_id, job_id = uuid4(), uuid4(), uuid4(), uuid4()
    content.create_project(
        project_id=project_id,
        user_id=user_id,
        title="Stale scene fence",
        description=None,
        source_language="en",
        target_scenes=1,
        status="completed",
        config={},
    )
    content.create_scene(
        scene_id=scene_id,
        project_id=project_id,
        scene_order=1,
        storyboard_text="Scene",
        voice_script="Scene",
        storyboard_status="approved",
    )
    old_scene = content.update_scene(
        scene_id,
        manim_code="OLD_CODE",
        manim_code_version=1,
        generation_status="completed",
    )
    assert old_scene is not None
    jobs.create_queued_job(
        job_id=job_id,
        project_id=project_id,
        scene_id=scene_id,
        job_type="full",
        render_quality="720p",
        docker_image_tag=None,
        metadata=scene_render_source(old_scene),
    )
    assert jobs.transition(job_id, expected_status="queued", status="rendering")

    content.update_scene(
        scene_id,
        manim_code="NEW_CODE",
        manim_code_version=2,
        generation_status="completed",
        video_url=None,
    )
    events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        "app.api.v1.internal.publish_project_event",
        lambda _project_id, event_type, payload: events.append((event_type, payload)) or True,
    )
    monkeypatch.setattr(settings, "supabase_storage_bucket", "videos")

    with pytest.raises(HTTPException, match="Render source changed") as raised:
        complete_render_job(
            job_id,
            {"asset_url": f"supabase://videos/{project_id}/renders/{job_id}.mp4"},
            jobs=jobs,
            content=content,
        )

    assert raised.value.status_code == 409
    current = content.get_scene(scene_id)
    assert current is not None and current.manim_code == "NEW_CODE"
    assert current.video_url is None
    failed = jobs.get(job_id)
    assert failed is not None and failed.status == "failed"
    assert failed.error_code == "stale_render_source"
    assert events and events[-1][0] == "render.failed"
    assert events[-1][1]["failure_stage"] == "source_fence"


def test_stale_full_project_render_is_failed_without_persisting(monkeypatch) -> None:
    redis = _redis()
    content = RedisContentStore(redis)
    jobs = RedisRenderJobStore(redis)
    user_id, project_id, job_id = uuid4(), uuid4(), uuid4()
    content.create_project(
        project_id=project_id,
        user_id=user_id,
        title="Stale project fence",
        description=None,
        source_language="en",
        target_scenes=2,
        status="completed",
        config={},
    )
    for order in (1, 2):
        scene = content.create_scene(
            scene_id=uuid4(),
            project_id=project_id,
            scene_order=order,
            storyboard_text=f"Scene {order}",
            voice_script=f"Scene {order}",
            storyboard_status="approved",
        )
        content.update_scene(
            scene.id,
            manim_code=f"CODE_{order}",
            generation_status="completed",
            video_url=f"supabase://videos/{project_id}/renders/scene-{order}-old.mp4",
        )
    initial_scenes = content.get_project_scenes(project_id)
    jobs.create_queued_job(
        job_id=job_id,
        project_id=project_id,
        scene_id=None,
        job_type="full_project",
        render_quality="720p",
        docker_image_tag=None,
        metadata=project_render_source(initial_scenes),
    )
    assert jobs.transition(job_id, expected_status="queued", status="rendering")

    first = initial_scenes[0]
    content.update_scene(
        first.id,
        manim_code="CHANGED_CODE",
        manim_code_version=first.manim_code_version + 1,
    )
    content.update_project(project_id, video_url=None)
    monkeypatch.setattr(settings, "supabase_storage_bucket", "videos")
    monkeypatch.setattr("app.api.v1.internal.publish_project_event", lambda *_args: True)

    with pytest.raises(HTTPException, match="Render source changed"):
        complete_render_job(
            job_id,
            {"asset_url": f"supabase://videos/{project_id}/renders/{job_id}.mp4"},
            jobs=jobs,
            content=content,
        )

    project = content.get_project(project_id)
    assert project is not None and project.video_url is None
    failed = jobs.get(job_id)
    assert failed is not None and failed.status == "failed"
    assert failed.error_code == "stale_render_source"


def test_current_full_project_render_persists_with_source_fence(monkeypatch) -> None:
    redis = _redis()
    content = RedisContentStore(redis)
    jobs = RedisRenderJobStore(redis)
    user_id, project_id, job_id = uuid4(), uuid4(), uuid4()
    content.create_project(
        project_id=project_id,
        user_id=user_id,
        title="Current project fence",
        description=None,
        source_language="en",
        target_scenes=1,
        status="completed",
        config={},
    )
    scene = content.create_scene(
        scene_id=uuid4(),
        project_id=project_id,
        scene_order=1,
        storyboard_text="Scene",
        voice_script="Scene",
        storyboard_status="approved",
    )
    content.update_scene(
        scene.id,
        manim_code="CODE",
        generation_status="completed",
        video_url=f"supabase://videos/{project_id}/renders/scene.mp4",
    )
    snapshot = project_render_source(content.get_project_scenes(project_id))
    jobs.create_queued_job(
        job_id=job_id,
        project_id=project_id,
        scene_id=None,
        job_type="full_project",
        render_quality="720p",
        docker_image_tag=None,
        metadata=snapshot,
    )
    assert jobs.transition(job_id, expected_status="queued", status="rendering")
    monkeypatch.setattr(settings, "supabase_storage_bucket", "videos")
    monkeypatch.setattr("app.api.v1.internal.publish_project_event", lambda *_args: True)
    asset_url = f"supabase://videos/{project_id}/renders/{job_id}.mp4"

    completed = complete_render_job(
        job_id,
        {"asset_url": asset_url},
        jobs=jobs,
        content=content,
    )

    assert completed["status"] == "completed"
    project = content.get_project(project_id)
    assert project is not None and project.video_url == asset_url


def test_active_render_dedupe_is_scoped_to_source_revision() -> None:
    redis = _redis()
    jobs = RedisRenderJobStore(redis)
    project_id, scene_id = uuid4(), uuid4()
    now = datetime.now(tz=UTC)
    first_scene = Scene(
        id=scene_id,
        project_id=project_id,
        scene_order=1,
        storyboard_status="approved",
        manim_code="OLD_CODE",
        manim_code_version=1,
        generation_status="completed",
        created_at=now,
        updated_at=now,
    )
    first, first_created = jobs.get_or_create_active_job(
        job_id=uuid4(),
        project_id=project_id,
        scene_id=scene_id,
        job_type="full",
        render_quality="720p",
        docker_image_tag=None,
        metadata=scene_render_source(first_scene),
    )
    second_scene = first_scene.model_copy(
        update={"manim_code": "NEW_CODE", "manim_code_version": 2}
    )
    second, second_created = jobs.get_or_create_active_job(
        job_id=uuid4(),
        project_id=project_id,
        scene_id=scene_id,
        job_type="full",
        render_quality="720p",
        docker_image_tag=None,
        metadata=scene_render_source(second_scene),
    )

    assert first_created is True and second_created is True
    assert first.id != second.id


def test_full_project_claim_converts_storage_objects_to_short_lived_urls(monkeypatch) -> None:
    monkeypatch.setattr(settings, "supabase_storage_bucket", "videos")
    calls: list[tuple[str, int | None]] = []

    def sign(*, object_path: str, expires_in_seconds: int | None = None) -> str:
        calls.append((object_path, expires_in_seconds))
        return f"https://signed.example/{object_path}"

    monkeypatch.setattr("app.api.v1.internal.sign_storage_object_read_url", sign)
    result = _render_worker_input_url("supabase://videos/project/renders/scene.mp4")
    assert result == "https://signed.example/project/renders/scene.mp4"
    assert calls == [
        ("project/renders/scene.mp4", settings.internal_render_signed_url_seconds)
    ]


def test_no_hitl_run_never_auto_approves_failed_builder_review(monkeypatch) -> None:
    now = datetime.now(tz=UTC)
    run = AiRun(
        id=uuid4(),
        project_id=uuid4(),
        scene_id=uuid4(),
        user_id=uuid4(),
        status="queued",
        hitl_enabled=False,
        created_at=now,
        updated_at=now,
    )
    generating = AgentStep(
        id=uuid4(),
        run_id=run.id,
        project_id=run.project_id,
        scene_id=run.scene_id,
        sequence=1,
        kind="builder",
        status="generating",
        input={},
        revision=1,
        created_at=now,
        updated_at=now,
    )

    class Store:
        def __init__(self) -> None:
            self.step = generating
            self.run_status = "queued"

        def complete(self, _step_id: UUID, *, draft_output: dict[str, Any]) -> AgentStep:
            self.step = self.step.model_copy(
                update={"status": "pending_review", "draft_output": draft_output}
            )
            return self.step

        def get_step(self, _step_id: UUID) -> AgentStep:
            return self.step

        def get_run(self, _run_id: UUID) -> AiRun:
            return run

        def list_runs(self, _project_id: UUID) -> list[AiRun]:
            return [run]

        def fail_pending_review(self, _step_id: UUID, *, error: str) -> AgentStep:
            self.step = self.step.model_copy(update={"status": "failed", "error": error})
            return self.step

        def update_run(self, _run_id: UUID, *, status: str) -> AiRun:
            self.run_status = status
            return run.model_copy(update={"status": status})

    class Content:
        def __init__(self) -> None:
            self.generation_status = "generating"
            self.project_status = "processing"

        def update_scene(self, _scene_id: UUID, **fields: Any) -> None:
            self.generation_status = str(fields["generation_status"])

        def update_project(self, _project_id: UUID, **fields: Any) -> None:
            if "status" in fields:
                self.project_status = str(fields["status"])

        def get_project(self, _project_id: UUID):  # noqa: ANN201
            return type("ProjectState", (), {"status": self.project_status, "updated_at": now})()

        def get_project_scenes(self, _project_id: UUID):  # noqa: ANN201
            return [type("SceneState", (), {"generation_status": self.generation_status})()]

        def update_project_if_current(
            self,
            _project_id: UUID,
            *,
            expected_updated_at: datetime,
            **fields: Any,
        ):  # noqa: ANN201
            _ = expected_updated_at
            self.project_status = str(fields["status"])
            return self.get_project(_project_id)

    store, content = Store(), Content()
    monkeypatch.setattr("app.api.v1.internal.publish_project_event", lambda *_args: True)
    monkeypatch.setattr(
        "app.api.v1.internal.pipeline_target_lock", lambda *_args: nullcontext()
    )
    result = complete_step(
        generating.id,
        InternalStepCompleteRequest(
            draft_output={
                "manim_code": "from manim import *",
                "auto_review": {
                    "code": {"passed": False, "final_error": "Unknown API"}
                },
            }
        ),
        store=store,  # type: ignore[arg-type]
        content=content,  # type: ignore[arg-type]
    )
    assert result["status"] == "failed"
    assert store.run_status == "failed"
    assert content.generation_status == "failed"
    assert content.project_status == "draft"


def test_no_hitl_auto_approval_requires_reviewed_builder_and_valid_storyboard() -> None:
    assert (
        _auto_approval_failure(
            "builder",
            {"manim_code": "from manim import *", "auto_review": {}},
        )
        == "Builder auto-review failed: top-level passed must be true"
    )
    assert (
        _auto_approval_failure(
            "builder",
            {
                "manim_code": "from manim import *",
                "auto_review": {"passed": True, "code": {"passed": False}},
            },
        )
        == "Builder code review failed: code review did not pass"
    )
    assert (
        _auto_approval_failure(
            "builder",
            {
                "manim_code": "from manim import *",
                "auto_review": {"passed": True, "code": {"passed": True}},
            },
        )
        == "Builder auto-review failed: visual review result is missing"
    )
    assert (
        _auto_approval_failure(
            "builder",
            {
                "manim_code": "from manim import *",
                "auto_review": {
                    "passed": True,
                    "code": {"passed": True},
                    "visual": {"passed": True},
                },
            },
        )
        is None
    )
    assert _auto_approval_failure("storyboarder", {"scenes": []}) is not None
    assert (
        _auto_approval_failure(
            "storyboarder",
            {
                "scenes": [
                    {
                        "scene_order": 0,
                        "narration": "Invalid zero-based scene",
                        "visual_action": "Draw",
                    }
                ]
            },
        )
        is not None
    )
    assert (
        _auto_approval_failure(
            "storyboarder",
            {
                "scenes": [
                    {
                        "scene_order": 1,
                        "narration": "Explain a limit",
                        "visual_action": "Animate the graph",
                    }
                ]
            },
        )
        is None
    )


def test_step_events_always_include_top_level_scene_id() -> None:
    class Step:
        scene_id = uuid4()

        def model_dump(self, *, mode: str) -> dict[str, str]:
            assert mode == "json"
            return {"id": "step"}

    payload = step_event_payload(Step(), review={"phase": "rendering"})
    assert payload["scene_id"] == str(Step.scene_id)
    assert payload["step"] == {"id": "step"}


def test_event_publish_is_fail_open(monkeypatch) -> None:
    class BrokenRedis:
        def publish(self, *_args: Any) -> None:
            raise RedisError("down")

    monkeypatch.setattr("app.services.events.get_redis", lambda: BrokenRedis())
    assert publish_project_event(str(uuid4()), "test.event", {}) is False


def test_read_through_cache_is_fail_open_when_redis_is_down() -> None:
    class BrokenRedis:
        def get(self, *_args: Any) -> None:
            raise RedisError("down")

        def setex(self, *_args: Any) -> None:
            raise RedisError("down")

        def delete(self, *_args: Any) -> None:
            raise RedisError("down")

        def pipeline(self, *_args: Any, **_kwargs: Any) -> Any:
            raise RedisError("down")

    cache = RedisJsonCache(BrokenRedis())  # type: ignore[arg-type]
    assert cache.get("key") is CACHE_MISS
    assert cache.generation("scope") == 0
    cache.set("key", {"value": 1})
    cache.delete("key")
    cache.bump("scope")


def test_correlation_id_is_preserved_on_error_response() -> None:
    response = TestClient(app, raise_server_exceptions=False).get(
        "/does-not-exist", headers={"X-Request-ID": "reliability-test"}
    )
    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "reliability-test"
    assert response.json()["error"]["request_id"] == "reliability-test"


def test_readiness_reports_redis_and_cached_supabase_reachability(monkeypatch) -> None:
    main_module = importlib.import_module("app.main")

    class RedisReady:
        def ping(self) -> bool:
            return True

    class SupabaseReady:
        def raise_for_status(self) -> None:
            return None

    calls = 0

    def get(*_args: Any, **_kwargs: Any) -> SupabaseReady:
        nonlocal calls
        calls += 1
        return SupabaseReady()

    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-key")
    monkeypatch.setattr(main_module, "get_redis", lambda: RedisReady())
    monkeypatch.setattr(main_module.httpx, "get", get)
    monkeypatch.setattr(main_module, "_supabase_readiness", (0.0, False, "not_checked"))

    first = main_module.ready()
    second = main_module.ready()
    payload = json.loads(first.body)
    assert first.status_code == second.status_code == 200
    assert payload["checks"]["redis"]["ok"] is True
    assert payload["checks"]["supabase"]["detail"] == "reachable"
    assert calls == 1


def test_production_readiness_requires_both_worker_queues(monkeypatch) -> None:
    main_module = importlib.import_module("app.main")

    class RedisReady:
        def ping(self) -> bool:
            return True

    class SupabaseReady:
        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-key")
    monkeypatch.setattr(main_module, "get_redis", lambda: RedisReady())
    monkeypatch.setattr(main_module.httpx, "get", lambda *_args, **_kwargs: SupabaseReady())
    monkeypatch.setattr(main_module, "check_worker_queues", lambda: (False, ("ai",)))
    monkeypatch.setattr(main_module, "_supabase_readiness", (0.0, False, "not_checked"))
    monkeypatch.setattr(main_module, "_worker_readiness", (0.0, False, ()))

    response = main_module.ready()
    payload = json.loads(response.body)
    assert response.status_code == 503
    assert payload["checks"]["workers"] == {
        "ok": False,
        "required": True,
        "queues": ["ai"],
    }


def test_websocket_manager_shutdown_closes_connections_and_listener() -> None:
    class Socket:
        def __init__(self) -> None:
            self.closed = False

        async def close(self, *, code: int, reason: str) -> None:
            assert code == 1001 and reason
            self.closed = True

    async def scenario() -> None:
        manager = ConnectionManager()
        socket = Socket()
        manager.active_connections = {"project": {socket}}  # type: ignore[dict-item]
        manager._pubsub_task = asyncio.create_task(asyncio.Event().wait())  # noqa: SLF001
        await manager.shutdown()
        assert socket.closed
        assert manager.connection_count == 0
        assert manager._pubsub_task is None  # noqa: SLF001

    asyncio.run(scenario())


def test_websocket_reconnect_during_last_disconnect_keeps_listener() -> None:
    class Socket:
        async def accept(self) -> None:
            return None

        async def close(self, *, code: int, reason: str) -> None:
            return None

    async def scenario() -> None:
        manager = ConnectionManager()
        old_socket, new_socket = Socket(), Socket()
        old_unwinding = asyncio.Event()
        release_old = asyncio.Event()
        replacement_wait = asyncio.Event()

        async def old_listener() -> None:
            try:
                await asyncio.Event().wait()
            finally:
                old_unwinding.set()
                await release_old.wait()

        async def replacement_listener() -> None:
            await replacement_wait.wait()

        manager.active_connections = {"project": {old_socket}}  # type: ignore[dict-item]
        old_task = asyncio.create_task(old_listener())
        manager._pubsub_task = old_task  # noqa: SLF001
        manager._listen_to_redis = replacement_listener  # type: ignore[method-assign]

        disconnecting = asyncio.create_task(manager.disconnect(old_socket, "project"))  # type: ignore[arg-type]
        await old_unwinding.wait()
        await manager.connect(new_socket, "project")  # type: ignore[arg-type]
        replacement_task = manager._pubsub_task  # noqa: SLF001
        release_old.set()
        await disconnecting

        assert replacement_task is not None
        assert replacement_task is manager._pubsub_task  # noqa: SLF001
        assert not replacement_task.done()
        replacement_wait.set()
        await manager.shutdown()

    asyncio.run(scenario())
