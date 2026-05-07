from __future__ import annotations

import logging

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from redis.exceptions import RedisError
from shared.pipeline_log import setup_pipeline_logging
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.api.v1.router import api_router
from backend.core.config import settings
from backend.core.correlation import CorrelationIdMiddleware
from backend.core.errors import register_exception_handlers
from backend.core.limiter import limiter
from backend.services.redis_client import get_redis

setup_pipeline_logging(level=settings.log_level, redis_url=settings.redis_url)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend.main")
logger.info(f"Initialized pipeline logging with level: {settings.log_level}")
logger.info(f"Backend started with LOG_LEVEL={settings.log_level}")

API_DESCRIPTION = """
# 🎬 Manim Agent API

Hệ thống điều phối (orchestration) cho quy trình sản xuất video Manim tự động bằng AI.

## Các tính năng chính:
- **Director Agent**: Lập kế hoạch storyboard từ ý tưởng ban đầu.
- **Planner Agent**: Chi tiết hóa storyboard thành các "beats" và "primitives".
- **Voice Synthesis**: Tích hợp TTS (Piper) để lồng tiếng tự động.
- **Builder Agent**: Tự động sinh mã nguồn Manim Python.
- **Review Loop**: Vòng lặp tự sửa lỗi code và review hình ảnh (visual review) bằng AI.

---
*Manim runs exclusively in worker processes.*

👉 **Thử nghiệm Premium API Client mới tại đây:** [/scalar](/scalar)
"""

# Manim Agent API - Redis connection optimized
app = FastAPI(
    title="Manim Agent API",
    version="0.1.0",
    description=API_DESCRIPTION,
    swagger_ui_parameters={
        "defaultModelsExpandDepth": -1,
        "persistAuthorization": True,
        "filter": True,
    },
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

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


@app.get("/scalar", include_in_schema=False)
def scalar_ui() -> HTMLResponse:
    """Premium API Client UI (Scalar)."""
    return HTMLResponse(
        content="""
        <!doctype html>
        <html>
          <head>
            <title>Manim Agent API - Scalar</title>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <style>
              body { margin: 0; }
            </style>
          </head>
          <body>
            <script
              id="api-reference"
              data-url="/openapi.json"></script>
            <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
          </body>
        </html>
        """
    )
