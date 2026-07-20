from __future__ import annotations

from pathlib import Path

import httpx

from app.core.config import settings


def upload_render_artifact(*, source_path: Path, object_path: str) -> str:
    """Upload a worker artifact using the Backend-only service role."""
    base = (settings.supabase_url or "").strip().rstrip("/")
    key = (settings.supabase_service_role_key or "").strip()
    bucket = settings.supabase_storage_bucket.strip()
    if not base or not key or not bucket:
        raise RuntimeError("Supabase Storage is not configured")
    if not source_path.is_file():
        raise RuntimeError("Render artifact is unavailable to Backend")
    response = httpx.post(
        f"{base}/storage/v1/object/{bucket}/{object_path}",
        headers={
            "Authorization": f"Bearer {key}",
            "apikey": key,
            "x-upsert": "true",
            "Content-Type": "video/mp4",
        },
        content=source_path.read_bytes(),
        timeout=120.0,
    )
    response.raise_for_status()
    return object_path


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
    if signed.startswith("/"):
        signed = f"{base}/storage/v1{signed}"
    return signed
