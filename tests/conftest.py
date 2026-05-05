from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from ai_engine.llm_client import FakeLLMClient, LiteLLMClient, LLMClient
from backend.core.config import settings
from backend.services.redis_client import configure_redis
from fakeredis import FakeRedis
from fastapi.testclient import TestClient


def _load_tests_env_file() -> None:
    """Optional `tests/.env.test`: vars for integration tests only (not in ``Settings``)."""
    paths = [
        Path(__file__).resolve().parent / ".env.test",
        Path(__file__).resolve().parents[1] / ".env",
    ]
    for path in paths:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if not key:
                continue
            if key not in os.environ:
                os.environ[key] = val


_load_tests_env_file()


@pytest.fixture(autouse=True)
def _disable_supabase_http_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests use FakeRedis only; avoid real PostgREST calls if `.env` has Supabase keys."""
    import backend.services.supabase_pipeline_rest as sp
    import backend.services.supabase_voice_rest as sv

    # Mock DB interactions
    monkeypatch.setattr(sv, "insert_voice_job_row", lambda *a, **k: None)
    monkeypatch.setattr(sv, "patch_voice_job_row", lambda *a, **k: None)
    monkeypatch.setattr(sv, "patch_scene_audio_row", lambda *a, **k: None)
    monkeypatch.setattr(sp, "insert_worker_service_audit_row", lambda *a, **k: None)
    monkeypatch.setattr(sp, "insert_pipeline_run_row", lambda *a, **k: None)

    # Mock storage uploads to return None by default (fallback to local file:// in tests)
    monkeypatch.setattr("worker.tts_runtime.upload_voice_artifact_if_configured", lambda **k: None)
    monkeypatch.setattr("worker.runtime.upload_render_artifact_if_configured", lambda **k: None)


@pytest.fixture(autouse=True)
def _isolate_redis_client_between_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test gets a fresh in-memory Redis and no real Supabase."""
    from backend.core.config import settings

    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_role_key", "")

    configure_redis(FakeRedis(decode_responses=True))
    yield
    configure_redis(None)


@pytest.fixture()
def llm_client() -> LLMClient:
    """Smart fixture: returns FakeLLMClient unless USE_REAL_LLM is set."""
    if os.getenv("USE_REAL_LLM") == "true":
        key = settings.openrouter_api_key or "fake_key"
        return LiteLLMClient(api_key=key)
    return FakeLLMClient()


@pytest.fixture()
def celery_config() -> dict[str, Any]:
    """Configure Celery for testing. Default is eager (sync)."""
    return {
        "broker_url": "memory://",
        "result_backend": "cache+memory://",
        "task_always_eager": True,
        "task_eager_propagates": True,
    }


@pytest.fixture()
def mock_supabase() -> MagicMock:
    """Mock Supabase client for testing."""
    mock = MagicMock()
    # Add common chain calls if needed
    mock.table.return_value.select.return_value.execute.return_value.data = []
    return mock


@pytest.fixture()
def api_client() -> TestClient:
    """Yields a FastAPI TestClient with dependencies overridden for offline testing."""
    from ai_engine.llm_client import FakeLLMClient
    from backend.api.deps import get_content_store, get_llm_client
    from backend.db.content_store import RedisContentStore
    from backend.main import app
    from backend.services.redis_client import get_redis
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient()
    app.dependency_overrides[get_content_store] = lambda: RedisContentStore(get_redis())
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
