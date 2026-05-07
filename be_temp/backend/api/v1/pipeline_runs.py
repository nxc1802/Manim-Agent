from __future__ import annotations

from typing import Any, cast
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException

from backend.api.access import project_readable_by_user
from backend.api.deps import get_content_store, get_request_user_id
from backend.core.config import settings
from backend.db.base import ContentStore

router = APIRouter(tags=["pipeline-runs"])


@router.get("/projects/{project_id}/pipeline-runs")
def list_project_pipeline_runs(
    project_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> list[dict[str, Any]]:
    project_readable_by_user(store, project_id, user_id)

    base = (settings.supabase_url or "").strip().rstrip("/")
    key = (settings.supabase_service_role_key or "").strip()
    if not base or not key:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    url = f"{base}/rest/v1/pipeline_runs"
    params = {"project_id": f"eq.{project_id}", "select": "*", "order": "created_at.desc"}
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(url, headers=headers, params=params)
            r.raise_for_status()
            return cast(list[dict[str, Any]], r.json())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
