from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
from shared.schemas.hitl import AgentStep, AgentStepKind, AiRun

from app.core.config import settings
from app.services.cache import CACHE_MISS, RedisJsonCache
from app.services.redis_client import get_redis
from app.services.supabase_http import supabase_admin_headers


class HitlStoreError(RuntimeError):
    pass


class SupabaseHitlStore:
    """Persistence adapter for durable HITL records.

    The API is the only process that owns this adapter. AI Core accesses the
    records exclusively through the internal HTTP endpoints below.
    """

    def __init__(
        self, base_url: str, service_key: str, cache: RedisJsonCache | None = None
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            **supabase_admin_headers(service_key),
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self._cache = cache or RedisJsonCache(get_redis())

    def _run_key(self, run_id: UUID) -> str:
        return self._cache.key("hitl", "run", run_id)

    def _step_key(self, step_id: UUID) -> str:
        return self._cache.key("hitl", "step", step_id)

    @staticmethod
    def _runs_scope(project_id: UUID) -> str:
        return f"hitl:project-runs:{project_id}"

    @staticmethod
    def _steps_scope(run_id: UUID) -> str:
        return f"hitl:run-steps:{run_id}"

    def _cache_run(self, run: AiRun) -> None:
        self._cache.set(self._run_key(run.id), run.model_dump(mode="json"))

    def _cache_step(self, step: AgentStep) -> None:
        self._cache.set(self._step_key(step.id), step.model_dump(mode="json"))

    @classmethod
    def from_settings(cls) -> SupabaseHitlStore:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise HitlStoreError("Supabase is required for durable HITL state")
        return cls(settings.supabase_url, settings.supabase_service_role_key)

    def _request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.request(
                    method,
                    f"{self._base_url}/rest/v1/{table}",
                    headers=self._headers,
                    params=params,
                    json=body,
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            raise HitlStoreError(f"HITL persistence request failed: {exc}") from exc
        if not isinstance(payload, list):
            raise HitlStoreError("Unexpected Supabase response for HITL record")
        return payload

    def create_run(
        self, *, project_id: UUID, scene_id: UUID | None, user_id: UUID, hitl_enabled: bool = True
    ) -> AiRun:
        now = datetime.now(tz=UTC).isoformat()
        rows = self._request(
            "POST",
            "ai_runs",
            body={
                "id": str(uuid4()),
                "project_id": str(project_id),
                "scene_id": str(scene_id) if scene_id else None,
                "user_id": str(user_id),
                "status": "queued",
                "hitl_enabled": hitl_enabled,
                "created_at": now,
                "updated_at": now,
            },
        )
        run = AiRun.model_validate(rows[0])
        self._cache_run(run)
        self._cache.bump(self._runs_scope(project_id))
        return run

    def get_run(self, run_id: UUID) -> AiRun | None:
        cached = self._cache.get(self._run_key(run_id))
        if cached is not CACHE_MISS:
            return AiRun.model_validate(cached) if cached is not None else None
        rows = self._request("GET", "ai_runs", params={"id": f"eq.{run_id}", "select": "*"})
        run = AiRun.model_validate(rows[0]) if rows else None
        self._cache.set(self._run_key(run_id), run.model_dump(mode="json") if run else None)
        return run

    def list_runs(self, project_id: UUID) -> list[AiRun]:
        generation = self._cache.generation(self._runs_scope(project_id))
        cache_key = self._cache.key("hitl", "runs", project_id, generation)
        cached = self._cache.get(cache_key)
        if cached is not CACHE_MISS and isinstance(cached, list):
            return [AiRun.model_validate(row) for row in cached]
        rows = self._request(
            "GET",
            "ai_runs",
            params={"project_id": f"eq.{project_id}", "select": "*", "order": "created_at.desc"},
        )
        runs = [AiRun.model_validate(row) for row in rows]
        self._cache.set(
            cache_key,
            [run.model_dump(mode="json") for run in runs],
            ttl_seconds=settings.cache_list_ttl_seconds,
        )
        return runs

    def update_run(self, run_id: UUID, *, status: str) -> AiRun | None:
        rows = self._request(
            "PATCH", "ai_runs", params={"id": f"eq.{run_id}"}, body={"status": status}
        )
        run = AiRun.model_validate(rows[0]) if rows else None
        if run is None:
            self._cache.delete(self._run_key(run_id))
            return None
        self._cache_run(run)
        self._cache.bump(self._runs_scope(run.project_id))
        return run

    def create_step(
        self,
        *,
        run: AiRun,
        sequence: int,
        kind: AgentStepKind,
        input_data: dict[str, Any],
    ) -> AgentStep:
        now = datetime.now(tz=UTC).isoformat()
        rows = self._request(
            "POST",
            "ai_steps",
            body={
                "id": str(uuid4()),
                "run_id": str(run.id),
                "project_id": str(run.project_id),
                "scene_id": str(run.scene_id) if run.scene_id else None,
                "sequence": sequence,
                "kind": kind,
                "status": "queued",
                "input": input_data,
                "revision": 1,
                "created_at": now,
                "updated_at": now,
            },
        )
        step = AgentStep.model_validate(rows[0])
        self._cache_step(step)
        self._cache.bump(self._steps_scope(run.id))
        return step

    def get_step(self, step_id: UUID) -> AgentStep | None:
        cached = self._cache.get(self._step_key(step_id))
        if cached is not CACHE_MISS:
            return AgentStep.model_validate(cached) if cached is not None else None
        rows = self._request("GET", "ai_steps", params={"id": f"eq.{step_id}", "select": "*"})
        step = AgentStep.model_validate(rows[0]) if rows else None
        self._cache.set(self._step_key(step_id), step.model_dump(mode="json") if step else None)
        return step

    def list_steps(self, run_id: UUID) -> list[AgentStep]:
        generation = self._cache.generation(self._steps_scope(run_id))
        cache_key = self._cache.key("hitl", "steps", run_id, generation)
        cached = self._cache.get(cache_key)
        if cached is not CACHE_MISS and isinstance(cached, list):
            return [AgentStep.model_validate(row) for row in cached]
        rows = self._request(
            "GET",
            "ai_steps",
            params={"run_id": f"eq.{run_id}", "select": "*", "order": "sequence.asc"},
        )
        steps = [AgentStep.model_validate(row) for row in rows]
        self._cache.set(
            cache_key,
            [step.model_dump(mode="json") for step in steps],
            ttl_seconds=settings.cache_list_ttl_seconds,
        )
        return steps

    def _transition(
        self,
        step_id: UUID,
        *,
        expected_status: str,
        expected_revision: int | None = None,
        values: dict[str, Any],
    ) -> AgentStep | None:
        params = {"id": f"eq.{step_id}", "status": f"eq.{expected_status}"}
        if expected_revision is not None:
            params["revision"] = f"eq.{expected_revision}"
        rows = self._request("PATCH", "ai_steps", params=params, body=values)
        step = AgentStep.model_validate(rows[0]) if rows else None
        if step is None:
            # A failed optimistic transition may mean another process won. Drop
            # the object cache so the next read observes the authoritative row.
            self._cache.delete(self._step_key(step_id))
            return None
        self._cache_step(step)
        self._cache.bump(self._steps_scope(step.run_id))
        return step

    def claim(self, step_id: UUID) -> AgentStep | None:
        return self._transition(step_id, expected_status="queued", values={"status": "generating"})

    def complete(self, step_id: UUID, *, draft_output: dict[str, Any]) -> AgentStep | None:
        return self._transition(
            step_id,
            expected_status="generating",
            values={"status": "pending_review", "draft_output": draft_output, "error": None},
        )

    def fail(self, step_id: UUID, *, error: str) -> AgentStep | None:
        return self._transition(
            step_id, expected_status="generating", values={"status": "failed", "error": error}
        )

    def fail_queued(self, step_id: UUID, *, error: str) -> AgentStep | None:
        """Fail work that was persisted but could not be published to the task broker."""
        return self._transition(
            step_id, expected_status="queued", values={"status": "failed", "error": error}
        )

    def fail_pending_review(self, step_id: UUID, *, error: str) -> AgentStep | None:
        """Fail a generated draft that cannot safely pass unattended review."""
        return self._transition(
            step_id,
            expected_status="pending_review",
            values={"status": "failed", "error": error},
        )

    def edit(
        self, step: AgentStep, *, draft_output: dict[str, Any], expected_revision: int
    ) -> AgentStep | None:
        return self._transition(
            step.id,
            expected_status="pending_review",
            expected_revision=expected_revision,
            values={"draft_output": draft_output, "revision": expected_revision + 1},
        )

    def approve(
        self, step: AgentStep, *, final_output: dict[str, Any], expected_revision: int
    ) -> AgentStep | None:
        return self._transition(
            step.id,
            expected_status="pending_review",
            expected_revision=expected_revision,
            values={
                "status": "approved",
                "final_output": final_output,
                "revision": expected_revision + 1,
            },
        )

    def reject(self, step: AgentStep, *, feedback: str, expected_revision: int) -> AgentStep | None:
        return self._transition(
            step.id,
            expected_status="pending_review",
            expected_revision=expected_revision,
            values={"status": "rejected", "error": feedback, "revision": expected_revision + 1},
        )

    def delete_steps_after(self, run_id: UUID, sequence: int) -> None:
        """Deletes all steps in a run that have a sequence greater than the given value."""
        deleted = self._request(
            "DELETE", "ai_steps", params={"run_id": f"eq.{run_id}", "sequence": f"gt.{sequence}"}
        )
        self._cache.delete(
            *(self._step_key(UUID(str(row["id"]))) for row in deleted if row.get("id"))
        )
        self._cache.bump(self._steps_scope(run_id))

    def cancel_unfinished_steps(self, run_id: UUID, *, reason: str) -> list[AgentStep]:
        """Fence queued or running callbacks when a parent artifact is rolled back."""
        updated = self._request(
            "PATCH",
            "ai_steps",
            params={
                "run_id": f"eq.{run_id}",
                "status": "in.(queued,generating,pending_review)",
            },
            body={"status": "failed", "error": reason[:4_000]},
        )
        steps = [AgentStep.model_validate(row) for row in updated]
        for step in steps:
            self._cache_step(step)
        self._cache.bump(self._steps_scope(run_id))
        return steps

    def revert_step(self, step_id: UUID) -> AgentStep | None:
        """Reverts a step's status back to pending_review."""
        # For a rollback, we bump revision to invalidate inflight frontend edits.
        rows = self._request(
            "GET", "ai_steps", params={"id": f"eq.{step_id}", "select": "revision"}
        )
        if not rows:
            return None
        current_revision = rows[0].get("revision", 1)
        params = {"id": f"eq.{step_id}"}
        values = {
            "status": "pending_review",
            "revision": current_revision + 1,
            "final_output": None,
            "error": None,
        }
        updated = self._request("PATCH", "ai_steps", params=params, body=values)
        step = AgentStep.model_validate(updated[0]) if updated else None
        if step is None:
            self._cache.delete(self._step_key(step_id))
            return None
        self._cache_step(step)
        self._cache.bump(self._steps_scope(step.run_id))
        return step
