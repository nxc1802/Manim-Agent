from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from backend.core.config import settings
from worker.supabase_storage import upload_render_artifact_if_configured


def test_upload_skips_when_supabase_not_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "supabase_url", None)
    monkeypatch.setattr(settings, "supabase_service_role_key", None)
    monkeypatch.setattr(settings, "supabase_storage_bucket", "videos")

    p = tmp_path / "a.mp4"
    p.write_bytes(b"x")
    pid = uuid4()
    jid = uuid4()
    assert upload_render_artifact_if_configured(video_path=p, project_id=pid, job_id=jid) is None
