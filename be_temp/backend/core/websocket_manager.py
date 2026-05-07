from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as redis
from fastapi import WebSocket

from backend.core.config import settings

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts Redis Pub/Sub events."""

    def __init__(self) -> None:
        self.active_connections: dict[str, list[WebSocket]] = {}
        self._redis_url = settings.redis_url
        self._pubsub_task: asyncio.Task[None] | None = None

    async def connect(self, websocket: WebSocket, scene_id: str) -> None:
        await websocket.accept()
        if scene_id not in self.active_connections:
            self.active_connections[scene_id] = []
        self.active_connections[scene_id].append(websocket)

        # Start pubsub listener if not already running
        if not self._pubsub_task:
            self._pubsub_task = asyncio.create_task(self._listen_to_redis())

    def disconnect(self, websocket: WebSocket, scene_id: str) -> None:
        if scene_id in self.active_connections:
            if websocket in self.active_connections[scene_id]:
                self.active_connections[scene_id].remove(websocket)
            if not self.active_connections[scene_id]:
                del self.active_connections[scene_id]

    async def _listen_to_redis(self) -> None:
        """Background task to listen to Redis 'manim_agent:events' and broadcast."""
        logger.info("Starting Redis Pub/Sub listener for WebSockets")
        r = redis.from_url(self._redis_url, decode_responses=True)  # type: ignore
        pubsub = r.pubsub()
        await pubsub.subscribe("manim_agent:events")

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    try:
                        payload = json.loads(data)
                        scene_id = payload.get("scene_id")
                        # Debug log to see what's coming in
                        logger.info(
                            f"WS Listener received: scene_id={scene_id}, "
                            f"active={list(self.active_connections.keys())}"
                        )

                        if scene_id and scene_id in self.active_connections:
                            logger.info(
                                f"Broadcasting to scene {scene_id}: {payload.get('message')}"
                            )
                            await self.broadcast_to_scene(scene_id, payload)
                    except Exception:
                        logger.exception("Failed to broadcast WebSocket message")
        finally:
            await pubsub.unsubscribe("manim_agent:events")
            await r.close()

    async def broadcast_to_scene(self, scene_id: str, message: Any) -> None:
        if scene_id in self.active_connections:
            # Create tasks for all sends to avoid blocking
            dead_connections = []
            for connection in self.active_connections[scene_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    dead_connections.append(connection)

            # Cleanup dead connections
            for dead in dead_connections:
                self.active_connections[scene_id].remove(dead)


# Global manager instance
manager = ConnectionManager()
