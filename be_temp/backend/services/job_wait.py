from __future__ import annotations

import time
from uuid import UUID

from shared.schemas.render_job import RenderJob

from backend.services.job_store import RedisRenderJobStore


def wait_for_render_job(
    job_store: RedisRenderJobStore,
    job_id: UUID,
    *,
    timeout_seconds: float,
    poll_interval_seconds: float = 0.5,
) -> RenderJob:
    """Poll Redis until the job reaches a terminal state or timeout."""
    deadline = time.monotonic() + max(timeout_seconds, 0.1)
    interval = max(poll_interval_seconds, 0.05)
    last: RenderJob | None = None
    while time.monotonic() < deadline:
        job = job_store.get(job_id)
        if job is None:
            msg = f"Render job disappeared: {job_id}"
            raise RuntimeError(msg)
        last = job
        if job.status in ("completed", "failed", "cancelled"):
            return job
        time.sleep(interval)
    st = last.status if last else "unknown"
    msg = f"Render job {job_id} timed out after {timeout_seconds}s (last_status={st})"
    raise TimeoutError(msg)
