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

import redis

LOG = logging.getLogger("manim.pipeline")

pipeline_trace_id_var: ContextVar[str | None] = ContextVar("pipeline_trace_id", default=None)

# Global Redis client for event broadcasting
_BROADCAST_REDIS: redis.Redis | None = None

def _get_broadcast_redis() -> redis.Redis | None:
    global _BROADCAST_REDIS
    if _BROADCAST_REDIS is not None:
        return _BROADCAST_REDIS
    url = os.environ.get("REDIS_URL")
    if not url:
        return None
    try:
        _BROADCAST_REDIS = redis.from_url(url, decode_responses=True)
        return _BROADCAST_REDIS
    except Exception:
        return None


def get_pipeline_trace_id() -> str | None:
    return pipeline_trace_id_var.get()


def _pipeline_log_level() -> int:
    """Read `LOG_LEVEL` (default `INFO`). Fallback to `PIPELINE_LOG_LEVEL` for backward compatibility."""
    raw = (os.environ.get("LOG_LEVEL") or os.environ.get("PIPELINE_LOG_LEVEL") or "INFO").strip().upper()
    return getattr(logging, raw, logging.INFO)


def setup_pipeline_logging(level: str | int | None = None) -> None:
    """Attach a single stdout handler so each event is one JSON line (idempotent)."""
    if LOG.handlers:
        return
    
    if level is not None:
        if isinstance(level, str):
            level = getattr(logging, level.upper(), logging.INFO)
    else:
        level = _pipeline_log_level()

    print(f"--- SETUP PIPELINE LOGGING: LEVEL={level} (DEBUG={logging.DEBUG}) ---", flush=True)

    LOG.setLevel(level)
    LOG.propagate = False
    
    # Also set root level to be sure
    logging.getLogger().setLevel(level)
    
    # JSON handler for structured logging
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOG.addHandler(handler)
    
    # Optional: If in DEBUG mode, add a human-readable stream for easier console reading
    if level == logging.DEBUG:
        console = logging.StreamHandler(sys.stderr) # Use stderr for human readable stuff to separate from JSON stdout
        console.setLevel(logging.DEBUG)
        fmt = logging.Formatter("\033[94m[%(levelname)s][%(name)s]\033[0m %(message)s")
        console.setFormatter(fmt)
        logging.getLogger("manim.human").addHandler(console)
        logging.getLogger("manim.human").setLevel(logging.DEBUG)


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


def _emit_human_readable(component: str, phase: str, message: str, details: dict[str, Any] | None) -> None:
    """Helper to print a beautiful block for developers in debug mode."""
    # Check if we should emit based on LOG level
    if LOG.level > logging.DEBUG:
        return
        
    separator = "═" * 80
    header = f" {component.upper()} | {phase.upper()} "
    
    # Use print for guaranteed visibility in console/nohup logs
    print(f"\n{separator}", file=sys.stderr)
    print(f"║{header:^78}║", file=sys.stderr)
    print(f"║ {message:<77}║", file=sys.stderr)
    print(f"{separator}", file=sys.stderr)
    
    if details:
        for k, v in details.items():
            val_str = str(v)
            if len(val_str) > 1000:
                val_str = val_str[:1000] + "... [TRUNCATED]"
            print(f"  ● {k.upper()}:", file=sys.stderr)
            # Indent multi-line content
            lines = val_str.splitlines()
            for line in lines:
                print(f"    {line}", file=sys.stderr)
    print(f"{separator}\n", file=sys.stderr)
    sys.stderr.flush()


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
    
    # Broadcast to Redis Pub/Sub
    r = _get_broadcast_redis()
    if r:
        try:
            r.publish("manim_agent:events", json.dumps(payload, default=str))
        except Exception:
            pass

    # Even in INFO mode, if it's an important event, show a summary
    if LOG.isEnabledFor(logging.DEBUG):
        _emit_human_readable(component, phase, message, details)


def pipeline_debug(
    component: str,
    phase: str,
    message: str,
    *,
    trace_id: str | None = None,
    details: dict[str, Any] | None = None,
    **fields: Any,
) -> None:
    """Verbose JSON lines; only emitted when ``LOG_LEVEL=DEBUG``."""
    payload = _pipeline_payload(
        component,
        phase,
        message,
        trace_id=trace_id,
        details=details,
        **fields,
    )
    LOG.debug(json.dumps(payload, default=str, ensure_ascii=False))
    
    # Broadcast to Redis Pub/Sub
    r = _get_broadcast_redis()
    if r:
        try:
            r.publish("manim_agent:events", json.dumps(payload, default=str))
        except Exception:
            pass
            
    _emit_human_readable(component, phase, message, details)
