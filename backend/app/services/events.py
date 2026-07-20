from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from redis.exceptions import RedisError

from app.core.config import settings
from app.services.redis_client import get_redis

logger = logging.getLogger(__name__)


def step_event_payload(step: Any, **extra: Any) -> dict[str, Any]:
    """Build the stable WebSocket payload shape used by every step event."""
    scene_id = getattr(step, "scene_id", None)
    payload = {
        "step": step.model_dump(mode="json"),
        "scene_id": str(scene_id) if scene_id else None,
    }
    payload.update(extra)
    return payload


def publish_project_event(project_id: str, event_type: str, payload: dict[str, Any]) -> bool:
    """Broadcast a state hint without making Redis Pub/Sub part of the write transaction."""
    message = {
        "id": str(uuid4()),
        "emitted_at": datetime.now(tz=UTC).isoformat(),
        "project_id": project_id,
        "type": event_type,
        "data": payload,
    }
    try:
        get_redis().publish(f"{settings.redis_prefix}:events", json.dumps(message, default=str))
    except (RedisError, OSError) as exc:
        # REST state remains authoritative. Clients recover by refetching after
        # reconnect, so an event outage must not turn a committed write into 500.
        logger.warning(
            "Project event publish failed project_id=%s type=%s error=%s",
            project_id,
            event_type,
            exc,
        )
        return False
    return True
