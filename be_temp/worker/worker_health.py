"""HTTP shell for Celery workers on cloud platforms (e.g. Hugging Face Spaces).

Cloud hosts expect an open HTTP port to mark the container Running. Celery has no HTTP
server, so we run **FastAPI** as the main process and spawn **Celery** in ``lifespan``
via ``subprocess.Popen``. Set ``WORKER_HEALTH_MODE`` to ``render`` (default) or ``tts``.
"""

from __future__ import annotations

import os
import socket
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from shared.pipeline_log import setup_pipeline_logging

setup_pipeline_logging()

_CELERY_APP = "worker.celery_app:celery_app"


def _celery_argv() -> list[str]:
    mode = (os.environ.get("WORKER_HEALTH_MODE") or "render").strip().lower()
    celery_log = (os.environ.get("CELERY_LOG_LEVEL") or "INFO").strip().upper()
    argv: list[str] = [
        "celery",
        "-A",
        _CELERY_APP,
        "worker",
        f"--loglevel={celery_log}",
        "--concurrency=1",
    ]
    if mode in ("tts", "tts-worker"):
        host = socket.gethostname()
        argv.extend(["-Q", "tts", "-n", f"tts@{host}"])
    else:
        argv.extend(["-Q", "render"])
    return argv


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    argv = _celery_argv()
    proc = subprocess.Popen(argv)  # noqa: S603
    app.state.proc = proc
    try:
        yield
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)


app = FastAPI(
    lifespan=lifespan,
    title="Manim Agent worker",
    description="Health HTTP for cloud schedulers; Celery runs as a child process.",
)


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "worker": "running"}


@app.get("/health")
def health() -> Response:
    proc = getattr(app.state, "proc", None)
    if proc is None or proc.poll() is not None:
        return Response(
            content='{"status": "error", "worker": "dead", "redis": false}',
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json",
        )

    # Check Redis
    from backend.services.redis_client import get_redis
    from redis.exceptions import RedisError

    try:
        get_redis().ping()
        return Response(
            content='{"status": "ok", "worker": "running", "redis": true}',
            status_code=status.HTTP_200_OK,
            media_type="application/json",
        )
    except (RedisError, OSError):
        return Response(
            content='{"status": "error", "worker": "running", "redis": false}',
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json",
        )
