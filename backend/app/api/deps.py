from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.supabase_jwt import JwtValidationError, user_id_from_supabase_jwt
from app.db.base import ContentStore
from app.db.content_store import get_content_store
from app.services.hitl_store import SupabaseHitlStore
from app.services.job_store import RedisRenderJobStore
from app.services.redis_client import get_redis

security = HTTPBearer(auto_error=False)


def get_job_store() -> RedisRenderJobStore:
    return RedisRenderJobStore(get_redis())


def get_hitl_store() -> SupabaseHitlStore:
    return SupabaseHitlStore.from_settings()


def get_request_user_id(
    auth: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
) -> UUID:
    """Resolve the caller without granting AI Core access to user credentials."""
    if settings.auth_mode != "jwt":
        return settings.dev_default_user_id
    if auth is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    secret = (settings.supabase_jwt_secret or "").strip()
    if not secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="JWT is not configured")
    try:
        return user_id_from_supabase_jwt(
            auth.credentials.strip(),
            secret=secret,
            audience=(settings.supabase_jwt_audience or "").strip() or None,
        )
    except JwtValidationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


__all__ = ["ContentStore", "get_content_store", "get_hitl_store", "get_job_store", "get_request_user_id"]
