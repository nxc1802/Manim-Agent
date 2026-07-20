from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from redis import Redis
from redis.exceptions import RedisError

from app.config import settings
from app.llm import configured_google_keys

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Manim AI Core",
    version="1.0.0",
    description="Private LLM, streaming and Manim rendering runtime. No database access.",
)


@app.middleware("http")
async def log_request(request: Request, call_next):  # type: ignore[no-untyped-def]
    request_id = (request.headers.get("x-request-id") or str(uuid4()))[:128]
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception:  # noqa: BLE001
        logger.exception(
            "AI Core request failed method=%s path=%s request_id=%s",
            request.method,
            request.url.path,
            request_id,
        )
        raise
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "AI Core request completed method=%s path=%s status=%d duration_ms=%.2f request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        (perf_counter() - started) * 1000,
        request_id,
    )
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-core"}


@app.get("/ready")
def ready() -> JSONResponse:
    checks: dict[str, object] = {}
    client: Redis | None = None
    try:
        client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=settings.readiness_timeout_seconds,
            socket_timeout=settings.readiness_timeout_seconds,
        )
        client.ping()
        checks["redis"] = {"ok": True}
    except (RedisError, OSError) as exc:
        logger.warning("AI Core Redis readiness failed error=%s", exc)
        checks["redis"] = {"ok": False}
    finally:
        if client is not None:
            client.close()

    try:
        import manim

        checks["manim"] = {
            "ok": True,
            "version": str(getattr(manim, "__version__", "unknown")),
        }
    except ImportError as exc:
        logger.error("AI Core Manim readiness failed error=%s", exc)
        checks["manim"] = {"ok": False, "version": None}

    checks["provider_keys"] = {"ok": bool(configured_google_keys())}
    all_ready = all(bool(check.get("ok")) for check in checks.values() if isinstance(check, dict))
    return JSONResponse(
        status_code=status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ready" if all_ready else "not_ready", "checks": checks},
    )
