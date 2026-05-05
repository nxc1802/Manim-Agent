from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx
from shared.schemas.review_pipeline import AgentLog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

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


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(httpx.HTTPError),
    reraise=True,
)
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

    usage = report.get("usage_summary") or {}
    pt = usage.get("total_prompt_tokens") or 0
    ct = usage.get("total_completion_tokens") or 0

    row = {
        "id": str(run_id),
        "project_id": str(project_id),
        "scene_id": str(scene_id),
        "status": status,
        "report": report,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": pt + ct,
    }
    url = f"{base}/rest/v1/pipeline_runs"
    try:
        # Pipeline runs need UPSERT
        put_headers = dict(headers)
        put_headers["Prefer"] = "return=minimal, resolution=merge-duplicates"
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, headers=put_headers, json=[row])
            r.raise_for_status()
    except Exception:
        logger.exception("Supabase insert pipeline_runs failed run_id=%s", run_id)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(httpx.HTTPError),
    reraise=True,
)
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

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(httpx.HTTPError),
    reraise=True,
)
def insert_agent_log_row(log: AgentLog) -> None:
    """Insert a single agent interaction log into Postgres."""
    headers = _service_headers()
    if headers is None:
        return
    base = (settings.supabase_url or "").strip().rstrip("/")
    full_url = f"{base}/rest/v1/agent_logs"
    payload = log.model_dump(mode="json")

    # Fallback: remote DB might not have 'attempt' or other new columns.
    # Move them into metrics JSONB to avoid 400 Bad Request if they are missing from DB.
    if payload.get("metrics") is None:
        payload["metrics"] = {}

    if "attempt" in payload:
        payload["metrics"]["attempt"] = payload.pop("attempt")

    # In case the remote DB is VERY old and missing output_text/error, we could pop them too,
    # but based on the schema they should be there. Let's keep them as columns for now.
    allowed_cols = [
        "id",
        "run_id",
        "scene_id",
        "round_idx",
        "agent_name",
        "prompt_version",
        "system_prompt",
        "user_prompt",
        "output_text",
        "error",
        "metrics",
    ]
    filtered_payload = {k: v for k, v in payload.items() if k in allowed_cols}

    try:
        # Agent logs might be retried, use UPSERT
        put_headers = dict(headers)
        put_headers["Prefer"] = "return=minimal, resolution=merge-duplicates"
        with httpx.Client(timeout=30.0) as client:
            r = client.post(full_url, headers=put_headers, json=[filtered_payload])
            if r.status_code >= 400:
                logger.error("Supabase error %s: %s", r.status_code, r.text)
            r.raise_for_status()
    except Exception:
        logger.exception("Supabase insert agent_logs failed run_id=%s", log.run_id)
