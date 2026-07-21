from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from typing import Any

import redis.asyncio as redis
from fastapi import WebSocket
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Project-scoped WebSocket fan-out backed by a resilient Redis listener."""

    def __init__(self) -> None:
        self.active_connections: dict[str, set[WebSocket]] = {}
        self._pubsub_task: asyncio.Task[None] | None = None

    async def connect(
        self,
        websocket: WebSocket,
        project_id: str,
        *,
        subprotocol: str | None = None,
    ) -> None:
        if subprotocol:
            await websocket.accept(subprotocol=subprotocol)
        else:
            await websocket.accept()
        self.active_connections.setdefault(project_id, set()).add(websocket)
        self._ensure_listener()
        logger.info(
            "WebSocket connected project_id=%s project_connections=%d total_connections=%d",
            project_id,
            len(self.active_connections[project_id]),
            self.connection_count,
        )

    async def disconnect(self, websocket: WebSocket, project_id: str) -> None:
        connections = self.active_connections.get(project_id)
        if connections is not None:
            connections.discard(websocket)
            if not connections:
                self.active_connections.pop(project_id, None)
        logger.info(
            "WebSocket disconnected project_id=%s total_connections=%d",
            project_id,
            self.connection_count,
        )
        if not self.active_connections:
            await self._stop_listener()
            # A new connect may arrive while the cancelled listener is unwinding.
            # Re-check after the await so no live socket is left without a relay.
            if self.active_connections:
                self._ensure_listener()

    @property
    def connection_count(self) -> int:
        return sum(len(connections) for connections in self.active_connections.values())

    def _ensure_listener(self) -> None:
        if self._pubsub_task is None or self._pubsub_task.done():
            self._pubsub_task = asyncio.create_task(
                self._listen_to_redis(), name="backend-project-events"
            )

    async def _stop_listener(self) -> None:
        task = self._pubsub_task
        self._pubsub_task = None
        if task is None or task.done() or task is asyncio.current_task():
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _listen_to_redis(self) -> None:
        reconnect_delay = 0.25
        try:
            while self.active_connections:
                client: redis.Redis | None = None
                pubsub: redis.client.PubSub | None = None
                try:
                    client = redis.from_url(
                        settings.redis_url,
                        decode_responses=True,
                        max_connections=settings.redis_max_connections,
                        health_check_interval=30,
                    )
                    pubsub = client.pubsub()
                    await pubsub.subscribe(f"{settings.redis_prefix}:events")
                    reconnect_delay = 0.25
                    logger.info("WebSocket Redis event listener subscribed")
                    async for message in pubsub.listen():
                        if not self.active_connections:
                            break
                        if message.get("type") != "message":
                            continue
                        try:
                            payload = json.loads(message["data"])
                            project_id = payload.get("project_id")
                            if isinstance(project_id, str):
                                await self.broadcast(project_id, payload)
                                if not self.active_connections:
                                    break
                        except (TypeError, ValueError, json.JSONDecodeError):
                            logger.exception("Unable to decode project event")
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "WebSocket Redis listener disconnected; retrying in %.2fs",
                        reconnect_delay,
                    )
                    if self.active_connections:
                        await asyncio.sleep(reconnect_delay)
                        reconnect_delay = min(
                            reconnect_delay * 2,
                            settings.websocket_redis_reconnect_max_seconds,
                        )
                finally:
                    if pubsub is not None:
                        with suppress(RedisError, OSError):
                            await pubsub.unsubscribe()
                        with suppress(RedisError, OSError):
                            await pubsub.aclose()
                    if client is not None:
                        with suppress(RedisError, OSError):
                            await client.aclose()
        finally:
            if self._pubsub_task is asyncio.current_task():
                self._pubsub_task = None
            logger.info("WebSocket Redis event listener stopped")

    async def broadcast(self, project_id: str, message: Any) -> None:
        connections = tuple(self.active_connections.get(project_id, set()))
        if not connections:
            return

        async def send(connection: WebSocket) -> WebSocket | None:
            try:
                await asyncio.wait_for(connection.send_json(message), timeout=5.0)
                return None
            except Exception:  # noqa: BLE001
                logger.warning("Dropping an unresponsive WebSocket project_id=%s", project_id)
                return connection

        dead = [item for item in await asyncio.gather(*(send(item) for item in connections)) if item]
        for connection in dead:
            current = self.active_connections.get(project_id)
            if current is not None:
                current.discard(connection)
                if not current:
                    self.active_connections.pop(project_id, None)

    async def shutdown(self) -> None:
        connections = [
            connection
            for project_connections in self.active_connections.values()
            for connection in project_connections
        ]
        self.active_connections.clear()
        await self._stop_listener()
        if connections:
            await asyncio.gather(
                *(connection.close(code=1001, reason="Backend shutting down") for connection in connections),
                return_exceptions=True,
            )


manager = ConnectionManager()
