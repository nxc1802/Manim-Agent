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


def _orchestrator_argv() -> list[str]:
    celery_log = (os.environ.get("CELERY_LOG_LEVEL") or "INFO").strip().upper()
    host = socket.gethostname()
    return [
        "celery",
        "-A",
        _CELERY_APP,
        "worker",
        f"--loglevel={celery_log}",
        "--concurrency=1",
        "-Q",
        "orchestrator",
        "-n",
        f"orchestrator@{host}",
    ]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    argv = _celery_argv()
    proc = subprocess.Popen(argv)  # noqa: S603
    app.state.proc = proc
    mode = (os.environ.get("WORKER_HEALTH_MODE") or "render").strip().lower()
    orchestrator_proc = None
    if mode not in ("tts", "tts-worker"):
        orchestrator_proc = subprocess.Popen(_orchestrator_argv())  # noqa: S603
    app.state.orchestrator_proc = orchestrator_proc
    try:
        yield
    finally:
        for worker_proc in (proc, orchestrator_proc):
            if worker_proc is None or worker_proc.poll() is not None:
                continue
            worker_proc.terminate()
            try:
                worker_proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                worker_proc.kill()
                worker_proc.wait(timeout=10)


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
    orchestrator_proc = getattr(app.state, "orchestrator_proc", None)
    if orchestrator_proc is not None and orchestrator_proc.poll() is not None:
        return Response(
            content='{"status": "error", "worker": "orchestrator_dead", "redis": false}',
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
