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

from fastapi import FastAPI

_CELERY_APP = "worker.celery_app:celery_app"


def _celery_argv() -> list[str]:
    mode = (os.environ.get("WORKER_HEALTH_MODE") or "render").strip().lower()
    argv: list[str] = [
        "celery",
        "-A",
        _CELERY_APP,
        "worker",
        "--loglevel=INFO",
        "--concurrency=1",
    ]
    if mode in ("tts", "tts-worker"):
        host = socket.gethostname()
        argv.extend(["-Q", "tts", "-n", f"tts@{host}"])
    else:
        argv.extend(["-Q", "render"])
    return argv


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    argv = _celery_argv()
    proc = subprocess.Popen(argv)  # noqa: S603
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
def health() -> dict[str, str]:
    return {"status": "ok", "worker": "running"}
