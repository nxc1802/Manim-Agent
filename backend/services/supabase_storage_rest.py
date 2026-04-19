from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)


def sign_storage_object_read_url(
    *,
    object_path: str,
    expires_in_seconds: int | None = None,
) -> str:
    """POST /storage/v1/object/sign/... using service role (server-side only)."""
    base = (settings.supabase_url or "").strip().rstrip("/")
    key = (settings.supabase_service_role_key or "").strip()
    bucket = settings.supabase_storage_bucket.strip()
    if not base or not key or not bucket:
        msg = "Supabase Storage is not configured"
        raise RuntimeError(msg)
    exp = int(expires_in_seconds or settings.supabase_signed_url_seconds)
    sign_url = f"{base}/storage/v1/object/sign/{bucket}/{object_path}"
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
    }
    with httpx.Client(timeout=60.0) as client:
        sign_resp = client.post(
            sign_url,
            headers=headers,
            json={"expiresIn": exp},
        )
        sign_resp.raise_for_status()
        payload = sign_resp.json()
    signed = payload.get("signedURL") or payload.get("signedUrl")
    if not isinstance(signed, str):
        msg = f"Unexpected Supabase sign response: {payload!r}"
        raise RuntimeError(msg)
    return signed


def upload_voice_wav_and_sign(
    *,
    wav_path: Path,
    project_id: UUID,
    job_id: UUID,
) -> str | None:
    """Upload scene TTS wav then return a signed read URL, or None if Supabase is not configured."""
    base = (settings.supabase_url or "").strip().rstrip("/")
    key = (settings.supabase_service_role_key or "").strip()
    bucket = settings.supabase_storage_bucket.strip()
    if not base or not key or not bucket:
        return None

    object_path = f"{project_id}/voice/{job_id}.wav"
    upload_url = f"{base}/storage/v1/object/{bucket}/{object_path}"
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "audio/wav",
        "x-upsert": "true",
    }

    try:
        data = wav_path.read_bytes()
        with httpx.Client(timeout=300.0) as client:
            upload_resp = client.post(upload_url, headers=headers, content=data)
            upload_resp.raise_for_status()
        return sign_storage_object_read_url(object_path=object_path)
    except Exception:
        logger.exception("Supabase upload/sign failed voice job_id=%s", job_id)
        return None


def upload_render_mp4_and_sign(
    *,
    video_path: Path,
    project_id: UUID,
    job_id: UUID,
) -> str | None:
    """Upload mp4 then return signed read URL, or None if Supabase is not configured."""
    base = (settings.supabase_url or "").strip().rstrip("/")
    key = (settings.supabase_service_role_key or "").strip()
    bucket = settings.supabase_storage_bucket.strip()
    if not base or not key or not bucket:
        return None

    object_path = f"{project_id}/renders/{job_id}.mp4"
    upload_url = f"{base}/storage/v1/object/{bucket}/{object_path}"
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "video/mp4",
        "x-upsert": "true",
    }

    try:
        data = video_path.read_bytes()
        with httpx.Client(timeout=300.0) as client:
            upload_resp = client.post(upload_url, headers=headers, content=data)
            upload_resp.raise_for_status()
        return sign_storage_object_read_url(object_path=object_path)
    except Exception:
        logger.exception("Supabase upload/sign failed job_id=%s", job_id)
        return None
