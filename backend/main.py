from __future__ import annotations

import logging

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from shared.pipeline_log import setup_pipeline_logging

from backend.api.v1.router import api_router
from backend.core.config import settings
from backend.core.correlation import CorrelationIdMiddleware
from backend.core.errors import register_exception_handlers
from backend.services.redis_client import get_redis

setup_pipeline_logging(level=settings.log_level)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend.main")
logger.info(f"Initialized pipeline logging with level: {settings.log_level}")
logger.info(f"Backend started with LOG_LEVEL={settings.log_level}")

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
def ready() -> JSONResponse:
    """Readiness probe; 503 when Redis (broker/job store) is unreachable."""
    try:
        get_redis().ping()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ready", "redis": True},
        )
    except (RedisError, OSError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "redis": False},
        )
