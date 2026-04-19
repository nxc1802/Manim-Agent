from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)


def _service_headers() -> dict[str, str] | None:
    base = (settings.supabase_url or "").strip().rstrip("/")
    key = (settings.supabase_service_role_key or "").strip()
    if not base or not key:
        return None
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def insert_pipeline_run_row(
    *,
    run_id: UUID,
    project_id: UUID,
    scene_id: UUID,
    status: str,
    report: dict[str, Any],
) -> None:
    """Mirror builder/review pipeline run to Postgres (PostgREST). No-op if not configured."""
    headers = _service_headers()
    if headers is None:
        return
    base = (settings.supabase_url or "").strip().rstrip("/")
    row = {
        "id": str(run_id),
        "project_id": str(project_id),
        "scene_id": str(scene_id),
        "status": status,
        "report": report,
    }
    url = f"{base}/rest/v1/pipeline_runs"
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, headers=headers, json=[row])
            r.raise_for_status()
    except Exception:
        logger.exception("Supabase insert pipeline_runs failed run_id=%s", run_id)


def insert_worker_service_audit_row(
    *,
    audit_id: UUID,
    project_id: UUID,
    scene_id: UUID | None,
    worker_kind: str,
    worker_name: str,
    payload: dict[str, Any],
    render_job_id: UUID | None = None,
    voice_job_id: UUID | None = None,
) -> None:
    """Worker-side audit (service role). JWT users rely on RLS SELECT for their projects."""
    headers = _service_headers()
    if headers is None:
        return
    base = (settings.supabase_url or "").strip().rstrip("/")
    row = {
        "id": str(audit_id),
        "project_id": str(project_id),
        "scene_id": str(scene_id) if scene_id else None,
        "render_job_id": str(render_job_id) if render_job_id else None,
        "voice_job_id": str(voice_job_id) if voice_job_id else None,
        "worker_kind": worker_kind,
        "worker_name": worker_name,
        "payload": payload,
    }
    url = f"{base}/rest/v1/worker_service_audit"
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, headers=headers, json=[row])
            r.raise_for_status()
    except Exception:
        logger.exception(
            "Supabase insert worker_service_audit failed kind=%s project=%s",
            worker_kind,
            project_id,
        )
