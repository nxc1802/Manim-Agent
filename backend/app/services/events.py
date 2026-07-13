from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.services.redis_client import get_redis


def publish_project_event(project_id: str, event_type: str, payload: dict[str, Any]) -> None:
    """Broadcast state changes; the WebSocket gateway fan-outs this channel."""
    message = {"project_id": project_id, "type": event_type, "data": payload}
    get_redis().publish(f"{settings.redis_prefix}:events", json.dumps(message, default=str))
