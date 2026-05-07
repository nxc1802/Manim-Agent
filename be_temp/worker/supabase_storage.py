from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from backend.services.supabase_storage_rest import (
    upload_render_mp4_and_sign,
    upload_voice_wav_and_sign,
)

logger = logging.getLogger(__name__)


def upload_render_artifact_if_configured(
    *,
    video_path: Path,
    project_id: UUID,
    job_id: UUID,
) -> str | None:
    """Upload rendered mp4 to Supabase Storage and return a signed URL (or None if not configured).

    Uses the Storage REST API with the **service role** key (worker only).
    """
    try:
        return upload_render_mp4_and_sign(
            video_path=video_path,
            project_id=project_id,
            job_id=job_id,
        )
    except Exception:
        logger.exception("Supabase upload/sign failed job_id=%s", job_id)
        return None


def upload_voice_artifact_if_configured(
    *,
    wav_path: Path,
    project_id: UUID,
    job_id: UUID,
) -> str | None:
    """Upload TTS wav to Supabase Storage and return signed URL (streaming-friendly)."""
    try:
        return upload_voice_wav_and_sign(
            wav_path=wav_path,
            project_id=project_id,
            job_id=job_id,
        )
    except Exception:
        logger.exception("Supabase voice upload/sign failed job_id=%s", job_id)
        return None
