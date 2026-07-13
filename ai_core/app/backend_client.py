from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from app.config import settings


class BackendClient:
    """AI Core's sole integration point. It never imports or opens Backend data."""

    def __init__(self) -> None:
        self._base_url = settings.backend_internal_url.rstrip("/")
        self._headers = {"X-Internal-Token": settings.internal_service_token}

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        with httpx.Client(timeout=120.0) as client:
            response = client.request(method, f"{self._base_url}{path}", headers=self._headers, json=body)
            response.raise_for_status()
            return dict(response.json())

    def claim_step(self, step_id: UUID) -> dict[str, Any]:
        return self._request("POST", f"/hitl-steps/{step_id}/claim")

    def stream_step_chunk(self, step_id: UUID, content_delta: str) -> None:
        self._request("POST", f"/hitl-steps/{step_id}/stream", {"content_delta": content_delta})

    def complete_step(self, step_id: UUID, draft_output: dict[str, Any]) -> None:
        self._request("POST", f"/hitl-steps/{step_id}/complete", {"draft_output": draft_output})

    def fail_step(self, step_id: UUID, error: str) -> None:
        self._request("POST", f"/hitl-steps/{step_id}/fail", {"error": error[:4000]})

    def claim_render(self, job_id: UUID) -> dict[str, Any]:
        return self._request("POST", f"/render-jobs/{job_id}/claim")

    def complete_render(self, job_id: UUID, asset_url: str) -> None:
        self._request("POST", f"/render-jobs/{job_id}/complete", {"asset_url": asset_url})

    def fail_render(self, job_id: UUID, error: str) -> None:
        self._request("POST", f"/render-jobs/{job_id}/fail", {"error": error[:4000]})
