from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.exceptions import RedisError

from backend.api.v1.router import api_router
from backend.core.config import settings
from backend.core.correlation import CorrelationIdMiddleware
from backend.core.errors import register_exception_handlers
from backend.services.redis_client import get_redis

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Manim Agent API",
    version="0.1.0",
    description="Orchestration API for AI-generated Manim videos (Manim runs in worker only).",
)

register_exception_handlers(app)

app.add_middleware(CorrelationIdMiddleware)

if settings.cors_origins_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix="/v1")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["health"])
def ready() -> dict[str, str | bool]:
    """Readiness probe; reports Redis connectivity (broker/job store)."""
    try:
        get_redis().ping()
        return {"status": "ready", "redis": True}
    except (RedisError, OSError):
        return {"status": "ready", "redis": False}
