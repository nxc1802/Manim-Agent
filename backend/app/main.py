from __future__ import annotations

import logging

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
from app.core.sentry_setup import init_sentry
from app.services.redis_client import get_redis

init_sentry()
logging.basicConfig(level=settings.log_level)

app = FastAPI(
    title="Manim Backend API",
    version="1.0.0",
    description=(
        "Backend owns identity, project data, durable HITL approvals and task dispatch. "
        "It contains no LLM, Manim or rendering implementation."
    ),
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
app.include_router(api_router, prefix="/v1")
app.include_router(internal_router, prefix="/internal", include_in_schema=False)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "backend"}


@app.get("/ready", tags=["health"])
def ready() -> JSONResponse:
    try:
        get_redis().ping()
        return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ready", "redis": True})
    except (RedisError, OSError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "redis": False},
        )
