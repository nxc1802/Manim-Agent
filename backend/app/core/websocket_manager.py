from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as redis
from fastapi import WebSocket

from app.core.config import settings

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket gateway for project-scoped state events published by Backend."""

    def __init__(self) -> None:
        self.active_connections: dict[str, list[WebSocket]] = {}
        self._pubsub_task: asyncio.Task[None] | None = None

    async def connect(self, websocket: WebSocket, project_id: str) -> None:
        await websocket.accept()
        self.active_connections.setdefault(project_id, []).append(websocket)
        if self._pubsub_task is None or self._pubsub_task.done():
            self._pubsub_task = asyncio.create_task(self._listen_to_redis())

    def disconnect(self, websocket: WebSocket, project_id: str) -> None:
        connections = self.active_connections.get(project_id, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self.active_connections.pop(project_id, None)

    async def _listen_to_redis(self) -> None:
        client = redis.from_url(settings.redis_url, decode_responses=True)
        pubsub = client.pubsub()
        await pubsub.subscribe(f"{settings.redis_prefix}:events")
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    payload = json.loads(message["data"])
                    project_id = payload.get("project_id")
                    if isinstance(project_id, str):
                        await self.broadcast(project_id, payload)
                except Exception:  # noqa: BLE001
                    logger.exception("Unable to relay project event")
        finally:
            await pubsub.unsubscribe()
            await client.aclose()

    async def broadcast(self, project_id: str, message: Any) -> None:
        dead: list[WebSocket] = []
        for connection in self.active_connections.get(project_id, []):
            try:
                await connection.send_json(message)
            except Exception:  # noqa: BLE001
                dead.append(connection)
        for connection in dead:
            self.disconnect(connection, project_id)


manager = ConnectionManager()
