from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from ai_engine.config import (
    AgentLLMParams,
    AgentName,
    RuntimeLimitsConfig,
    default_agent_models_path,
    load_agent_models_yaml,
    load_runtime_limits,
    resolve_agent_params,
)
from ai_engine.llm_client import FakeLLMClient, LiteLLMClient, LLMClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.core.config import settings
from backend.core.supabase_jwt import JwtValidationError, user_id_from_supabase_jwt
from backend.db.base import ContentStore
from backend.db.content_store import get_content_store as get_content_store
from backend.services.job_store import RedisRenderJobStore
from backend.services.redis_client import get_redis
from backend.services.scene_service import SceneService
from backend.services.voice_job_store import RedisVoiceJobStore

security = HTTPBearer(auto_error=False)


def get_job_store() -> RedisRenderJobStore:
    return RedisRenderJobStore(get_redis())


def get_voice_job_store() -> RedisVoiceJobStore:
    return RedisVoiceJobStore(get_redis())


def _resolved_agent_models_path() -> Path:
    if settings.agent_models_yaml:
        return Path(settings.agent_models_yaml).expanduser()
    return default_agent_models_path()


def get_agent_llm_params(agent: AgentName) -> AgentLLMParams:
    data = load_agent_models_yaml(_resolved_agent_models_path())
    return resolve_agent_params(data, agent)


def get_runtime_limits() -> RuntimeLimitsConfig:
    data = load_agent_models_yaml(_resolved_agent_models_path())
    return load_runtime_limits(data)


def get_llm_client() -> LLMClient:
    """Use LiteLLM when any configured provider has credentials."""
    key = (settings.openrouter_api_key or "").strip() or None
    ds_key = (settings.dashscope_api_key or "").strip() or None
    google_key = (settings.google_api_key or "").strip() or None
    has_google_suffix_key = any(
        bool(os.environ.get(f"GOOGLE_API_KEY_{index}")) for index in range(1, 100)
    )
    if key or ds_key or google_key or has_google_suffix_key:
        provider_bases = {}
        if settings.openrouter_api_base:
            provider_bases["openrouter"] = settings.openrouter_api_base
        if settings.dashscope_api_base:
            provider_bases["dashscope"] = settings.dashscope_api_base

        provider_keys = {}
        if ds_key:
            provider_keys["dashscope"] = ds_key
        if google_key:
            provider_keys["google_ai_studio"] = google_key
        return LiteLLMClient(
            key,
            api_base=settings.llm_api_base,
            provider_keys=provider_keys or None,
            provider_bases=provider_bases if provider_bases else None,
        )
    return FakeLLMClient()


def get_scene_service(
    store: ContentStore = Depends(get_content_store),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
    job_store: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
    vstore: RedisVoiceJobStore = Depends(get_voice_job_store),  # noqa: B008
) -> SceneService:
    return SceneService(store=store, llm=llm, job_store=job_store, vstore=vstore)


def get_request_user_id(
    auth: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
) -> UUID:
    """Resolve the acting user: dev default when AUTH_MODE=off; JWT sub when AUTH_MODE=jwt."""
    if settings.auth_mode != "jwt":
        return settings.dev_default_user_id

    if not auth:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header (Bearer token required)",
        )

    token = auth.credentials.strip()
    secret = (settings.supabase_jwt_secret or "").strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT validation is not configured (SUPABASE_JWT_SECRET)",
        )
    aud = (settings.supabase_jwt_audience or "").strip() or None
    try:
        return user_id_from_supabase_jwt(token, secret=secret, audience=aud)
    except JwtValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
