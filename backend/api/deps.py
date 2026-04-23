from __future__ import annotations

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
from fastapi import Header, HTTPException, status

from backend.core.config import settings
from backend.core.supabase_jwt import JwtValidationError, user_id_from_supabase_jwt
from backend.services.content_store import RedisContentStore, get_content_store
from backend.services.job_store import RedisRenderJobStore
from backend.services.redis_client import get_redis
from backend.services.voice_job_store import RedisVoiceJobStore


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
    """Use LiteLLM when ``OPENROUTER_API_KEY`` is set; otherwise ``FakeLLMClient`` (offline)."""
    key = (settings.openrouter_api_key or "").strip() or None
    if key:
        return LiteLLMClient(key, api_base=settings.llm_api_base)
    return FakeLLMClient()


def get_request_user_id(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> UUID:
    """Resolve the acting user: dev default when AUTH_MODE=off; JWT sub when AUTH_MODE=jwt."""
    if settings.auth_mode != "jwt":
        return settings.dev_default_user_id
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = authorization.split(" ", 1)[1].strip()
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
