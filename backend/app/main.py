from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from time import monotonic
from typing import Any

import httpx
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.router import api_router, internal_router
from app.core.config import settings
from app.core.correlation import CorrelationIdMiddleware
from app.core.errors import register_exception_handlers
from app.core.limiter import limiter
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.sentry_setup import init_sentry
from app.core.static_spa import mount_static_spa
from app.core.websocket_manager import manager
from app.services.ai_queue import check_worker_queues
from app.services.redis_client import close_redis, get_redis
from app.services.supabase_http import supabase_admin_headers

init_sentry()
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

_supabase_readiness: tuple[float, bool, str] = (0.0, False, "not_checked")
_worker_readiness: tuple[float, bool, tuple[str, ...]] = (0.0, False, ())


def _check_supabase_reachability() -> tuple[bool, str]:
    global _supabase_readiness
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return False, "not_configured"
    now = monotonic()
    checked_at, reachable, detail = _supabase_readiness
    if now - checked_at < settings.readiness_cache_seconds:
        return reachable, detail
    try:
        response = httpx.get(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/projects",
            headers=supabase_admin_headers(settings.supabase_service_role_key),
            params={"select": "id", "limit": "1"},
            timeout=settings.readiness_timeout_seconds,
        )
        response.raise_for_status()
        result = (True, "reachable")
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("Supabase readiness probe failed error=%s", exc)
        result = (False, "unreachable")
    _supabase_readiness = (now, *result)
    return result


def _check_worker_reachability() -> tuple[bool, tuple[str, ...]]:
    global _worker_readiness
    now = monotonic()
    checked_at, reachable, queues = _worker_readiness
    if now - checked_at < settings.readiness_cache_seconds:
        return reachable, queues
    reachable, queues = check_worker_queues()
    _worker_readiness = (now, reachable, queues)
    return reachable, queues


@asynccontextmanager
async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
    yield
    await manager.shutdown()
    close_redis()

app = FastAPI(
    title="Manim Backend API",
    version="1.0.0",
    description=(
        "Backend owns identity, project data, durable HITL approvals and task dispatch. "
        "It contains no LLM, Manim or rendering implementation."
    ),
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
register_exception_handlers(app)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SecurityHeadersMiddleware,
    enable_hsts=settings.app_env.lower() in {"production", "prod", "staging"},
)
app.include_router(api_router, prefix="/v1")
app.include_router(internal_router, prefix="/internal", include_in_schema=False)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "backend"}


@app.get("/ready", tags=["health"])
def ready() -> JSONResponse:
    checks: dict[str, Any] = {}
    try:
        get_redis().ping()
        checks["redis"] = {"ok": True}
    except (RedisError, OSError):
        checks["redis"] = {"ok": False}

    supabase_ok, supabase_detail = _check_supabase_reachability()
    checks["supabase"] = {
        "ok": supabase_ok,
        "configured": bool(settings.supabase_url and settings.supabase_service_role_key),
        "detail": supabase_detail,
    }
    checks["content_store"] = {
        "ok": supabase_ok or settings.app_env.lower() == "development",
        "mode": "supabase" if settings.supabase_url else "redis_development",
    }
    checks["hitl_store"] = {"ok": supabase_ok, "mode": "supabase"}
    checks["task_queue"] = {"ok": checks["redis"]["ok"], "broker": "redis"}

    require_workers = settings.app_env.lower() in {"production", "prod", "staging"}
    worker_ok, worker_queues = (
        _check_worker_reachability() if require_workers else (True, ())
    )
    checks["workers"] = {
        "ok": worker_ok,
        "required": require_workers,
        "queues": list(worker_queues),
    }

    all_ready = bool(
        checks["redis"]["ok"] and checks["hitl_store"]["ok"] and worker_ok
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ready" if all_ready else "not_ready", "checks": checks},
    )


# Keep this mount last. Starlette resolves routes in registration order, so the
# API, internal callbacks, health probes, and OpenAPI UI remain authoritative.
mount_static_spa(app)
