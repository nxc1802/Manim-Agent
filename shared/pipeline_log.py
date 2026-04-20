"""Structured one-line JSON logs for cross-service debugging (e.g. Hugging Face Space logs).

Filter logs by logger ``manim.pipeline`` or JSON field ``trace_id`` to follow API → worker steps.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

LOG = logging.getLogger("manim.pipeline")

pipeline_trace_id_var: ContextVar[str | None] = ContextVar("pipeline_trace_id", default=None)


def get_pipeline_trace_id() -> str | None:
    return pipeline_trace_id_var.get()


def _pipeline_log_level() -> int:
    """``PIPELINE_LOG_LEVEL`` (default ``INFO``): level for logger ``manim.pipeline``."""
    raw = (os.environ.get("PIPELINE_LOG_LEVEL") or "INFO").strip().upper()
    return getattr(logging, raw, logging.INFO)


def setup_pipeline_logging() -> None:
    """Attach a single stdout handler so each event is one JSON line (idempotent)."""
    if LOG.handlers:
        return
    level = _pipeline_log_level()
    LOG.setLevel(level)
    LOG.propagate = False
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOG.addHandler(handler)


def _pipeline_payload(
    component: str,
    phase: str,
    message: str,
    *,
    trace_id: str | None = None,
    details: dict[str, Any] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    tid = trace_id if trace_id is not None else get_pipeline_trace_id()
    payload: dict[str, Any] = {
        "ts": datetime.now(tz=UTC).isoformat(),
        "component": component,
        "phase": phase,
        "message": message,
    }
    if tid:
        payload["trace_id"] = tid
    if details:
        payload["details"] = details
    for key, value in fields.items():
        if value is not None:
            payload[key] = value
    return payload


def trace_id_from_celery_request(request: object | None) -> str | None:
    """Read ``trace_id`` from Celery :attr:`Task.request`."""
    if request is None:
        return None
    raw = getattr(request, "headers", None)
    if raw is None:
        return None
    getter = getattr(raw, "get", None)
    if not callable(getter):
        return None
    tid = getter("trace_id")
    if tid is None:
        tid = getter("Trace_id")
    if isinstance(tid, str) and tid.strip():
        return tid.strip()
    return None


def celery_trace_headers(trace_id: str | None) -> dict[str, str]:
    tid = trace_id.strip() if isinstance(trace_id, str) and trace_id.strip() else None
    if tid:
        return {"trace_id": tid}
    return {}


def pipeline_event(
    component: str,
    phase: str,
    message: str,
    *,
    trace_id: str | None = None,
    details: dict[str, Any] | None = None,
    **fields: Any,
) -> None:
    """Main pipeline milestones (typically visible at **INFO**)."""
    payload = _pipeline_payload(
        component,
        phase,
        message,
        trace_id=trace_id,
        details=details,
        **fields,
    )
    LOG.info(json.dumps(payload, default=str, ensure_ascii=False))


def pipeline_debug(
    component: str,
    phase: str,
    message: str,
    *,
    trace_id: str | None = None,
    details: dict[str, Any] | None = None,
    **fields: Any,
) -> None:
    """Verbose JSON lines; only emitted when ``PIPELINE_LOG_LEVEL=DEBUG``."""
    payload = _pipeline_payload(
        component,
        phase,
        message,
        trace_id=trace_id,
        details=details,
        **fields,
    )
    LOG.debug(json.dumps(payload, default=str, ensure_ascii=False))
