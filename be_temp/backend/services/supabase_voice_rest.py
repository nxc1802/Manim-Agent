from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from shared.schemas.voice_job import VoiceJob

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


def insert_voice_job_row(job: VoiceJob) -> None:
    """Insert queued voice job into Postgres (PostgREST). No-op if Supabase is not configured."""
    headers = _service_headers()
    if headers is None:
        return
    base = (settings.supabase_url or "").strip().rstrip("/")
    row = {
        "id": str(job.id),
        "project_id": str(job.project_id),
        "scene_id": str(job.scene_id),
        "status": job.status,
        "progress": job.progress,
        "logs": job.logs,
        "asset_url": job.asset_url,
        "error_code": job.error_code,
        "metadata": job.metadata,
        "voice_engine": job.voice_engine,
        "docker_image_tag": job.docker_image_tag,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
    url = f"{base}/rest/v1/voice_jobs"
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, headers=headers, json=[row])
            r.raise_for_status()
    except Exception:
        logger.exception("Supabase insert voice_jobs failed job_id=%s", job.id)


def patch_voice_job_row(job: VoiceJob) -> None:
    headers = _service_headers()
    if headers is None:
        return
    base = (settings.supabase_url or "").strip().rstrip("/")
    body: dict[str, Any] = {
        "status": job.status,
        "progress": job.progress,
        "logs": job.logs,
        "asset_url": job.asset_url,
        "error_code": job.error_code,
        "metadata": job.metadata,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
    url = f"{base}/rest/v1/voice_jobs?id=eq.{job.id}"
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.patch(url, headers=headers, json=body)
            r.raise_for_status()
    except Exception:
        logger.exception("Supabase patch voice_jobs failed job_id=%s", job.id)


def patch_scene_audio_row(
    *,
    scene_id: UUID,
    audio_url: str | None,
    timestamps: dict[str, Any] | None,
    duration_seconds: Decimal | None,
    voice_script: str | None = None,
    update_voice_script: bool = False,
) -> None:
    """Mirror scene audio fields to Postgres `scenes` (optional)."""
    headers = _service_headers()
    if headers is None:
        return
    base = (settings.supabase_url or "").strip().rstrip("/")
    body: dict[str, Any] = {
        "audio_url": audio_url,
        "timestamps": timestamps,
        "duration_seconds": float(duration_seconds) if duration_seconds is not None else None,
    }
    if update_voice_script:
        body["voice_script"] = voice_script
    url = f"{base}/rest/v1/scenes?id=eq.{scene_id}"
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.patch(url, headers=headers, json=body)
            r.raise_for_status()
    except Exception:
        logger.exception("Supabase patch scenes audio failed scene_id=%s", scene_id)
