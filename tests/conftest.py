from __future__ import annotations

import pytest
from backend.services.redis_client import configure_redis
from fakeredis import FakeRedis


@pytest.fixture(autouse=True)
def _disable_supabase_http_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests use FakeRedis only; avoid real PostgREST calls if `.env` has Supabase keys."""
    import backend.services.supabase_pipeline_rest as sp
    import backend.services.supabase_voice_rest as sv

    monkeypatch.setattr(sv, "insert_voice_job_row", lambda *a, **k: None)
    monkeypatch.setattr(sv, "patch_voice_job_row", lambda *a, **k: None)
    monkeypatch.setattr(sv, "patch_scene_audio_row", lambda *a, **k: None)
    monkeypatch.setattr(sp, "insert_worker_service_audit_row", lambda *a, **k: None)
    monkeypatch.setattr(sp, "insert_pipeline_run_row", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def _isolate_redis_client_between_tests() -> None:
    """Every test gets a fresh in-memory Redis (no local daemon required)."""
    configure_redis(FakeRedis(decode_responses=True))
    yield
    configure_redis(None)
