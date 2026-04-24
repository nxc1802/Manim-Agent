from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from backend.services.supabase_voice_rest import insert_voice_job_row, patch_voice_job_row
from shared.schemas.voice_job import VoiceJob


def test_voice_job_rest_noop_without_supabase() -> None:
    job = VoiceJob(
        id=uuid4(),
        project_id=uuid4(),
        scene_id=uuid4(),
        status="queued",
        progress=0,
        metadata={"synthesis_text": "x"},
        voice_engine="piper",
        created_at=datetime.now(tz=UTC),
    )
    insert_voice_job_row(job)
    patch_voice_job_row(job)
