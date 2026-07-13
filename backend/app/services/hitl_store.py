from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
from shared.schemas.hitl import AgentStep, AgentStepKind, AiRun

from app.core.config import settings


class HitlStoreError(RuntimeError):
    pass


class SupabaseHitlStore:
    """Persistence adapter for durable HITL records.

    The API is the only process that owns this adapter. AI Core accesses the
    records exclusively through the internal HTTP endpoints below.
    """

    def __init__(self, base_url: str, service_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

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

    def create_run(self, *, project_id: UUID, scene_id: UUID | None, user_id: UUID, hitl_enabled: bool = True) -> AiRun:
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
        return AiRun.model_validate(rows[0])

    def get_run(self, run_id: UUID) -> AiRun | None:
        rows = self._request("GET", "ai_runs", params={"id": f"eq.{run_id}", "select": "*"})
        return AiRun.model_validate(rows[0]) if rows else None

    def list_runs(self, project_id: UUID) -> list[AiRun]:
        rows = self._request(
            "GET",
            "ai_runs",
            params={"project_id": f"eq.{project_id}", "select": "*", "order": "created_at.desc"},
        )
        return [AiRun.model_validate(row) for row in rows]

    def update_run(self, run_id: UUID, *, status: str) -> AiRun | None:
        rows = self._request(
            "PATCH", "ai_runs", params={"id": f"eq.{run_id}"}, body={"status": status}
        )
        return AiRun.model_validate(rows[0]) if rows else None

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
                "scene_id": str(run.scene_id),
                "sequence": sequence,
                "kind": kind,
                "status": "queued",
                "input": input_data,
                "revision": 1,
                "created_at": now,
                "updated_at": now,
            },
        )
        return AgentStep.model_validate(rows[0])

    def get_step(self, step_id: UUID) -> AgentStep | None:
        rows = self._request("GET", "ai_steps", params={"id": f"eq.{step_id}", "select": "*"})
        return AgentStep.model_validate(rows[0]) if rows else None

    def list_steps(self, run_id: UUID) -> list[AgentStep]:
        rows = self._request(
            "GET", "ai_steps", params={"run_id": f"eq.{run_id}", "select": "*", "order": "sequence.asc"}
        )
        return [AgentStep.model_validate(row) for row in rows]

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
        return AgentStep.model_validate(rows[0]) if rows else None

    def claim(self, step_id: UUID) -> AgentStep | None:
        return self._transition(step_id, expected_status="queued", values={"status": "generating"})

    def complete(self, step_id: UUID, *, draft_output: dict[str, Any]) -> AgentStep | None:
        return self._transition(
            step_id,
            expected_status="generating",
            values={"status": "pending_review", "draft_output": draft_output, "error": None},
        )

    def fail(self, step_id: UUID, *, error: str) -> AgentStep | None:
        return self._transition(step_id, expected_status="generating", values={"status": "failed", "error": error})

    def edit(self, step: AgentStep, *, draft_output: dict[str, Any], expected_revision: int) -> AgentStep | None:
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
        self._request("DELETE", "ai_steps", params={"run_id": f"eq.{run_id}", "sequence": f"gt.{sequence}"})

    def revert_step(self, step_id: UUID) -> AgentStep | None:
        """Reverts a step's status back to pending_review."""
        # For a rollback, we bump revision to invalidate inflight frontend edits.
        rows = self._request("GET", "ai_steps", params={"id": f"eq.{step_id}", "select": "revision"})
        if not rows:
            return None
        current_revision = rows[0].get("revision", 1)
        params = {"id": f"eq.{step_id}"}
        values = {"status": "pending_review", "revision": current_revision + 1}
        updated = self._request("PATCH", "ai_steps", params=params, body=values)
        return AgentStep.model_validate(updated[0]) if updated else None
