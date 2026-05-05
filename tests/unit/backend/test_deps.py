from __future__ import annotations

from uuid import UUID

import pytest
from backend.api.deps import (
    get_agent_llm_params,
    get_job_store,
    get_llm_client,
    get_request_user_id,
    get_runtime_limits,
    get_voice_job_store,
)
from backend.core.config import settings
from fastapi import HTTPException


def test_get_stores():
    assert get_job_store() is not None
    assert get_voice_job_store() is not None


def test_get_llm_client(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    monkeypatch.setattr(settings, "dashscope_api_key", "")
    from ai_engine.llm_client import FakeLLMClient, LiteLLMClient

    assert isinstance(get_llm_client(), FakeLLMClient)

    monkeypatch.setattr(settings, "openrouter_api_key", "sk-123")
    assert isinstance(get_llm_client(), LiteLLMClient)


def test_get_request_user_id_dev(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "off")
    uid = get_request_user_id(None)
    assert isinstance(uid, UUID)
    assert uid == settings.dev_default_user_id


def test_get_request_user_id_jwt_fail(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "jwt")

    # Missing auth
    with pytest.raises(HTTPException) as exc:
        get_request_user_id(None)
    assert exc.value.status_code == 401

    # Missing secret
    monkeypatch.setattr(settings, "supabase_jwt_secret", "")
    from dataclasses import dataclass

    @dataclass
    class Auth:
        credentials: str

    with pytest.raises(HTTPException) as exc:
        get_request_user_id(Auth(credentials="tok"))
    assert exc.value.status_code == 503


def test_get_runtime_limits():
    limits = get_runtime_limits()
    assert limits.llm_timeout_default_seconds > 0


def test_get_agent_llm_params():
    params = get_agent_llm_params("builder")
    assert params.model
