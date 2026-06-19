from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.websocket_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/{scene_id}")
async def websocket_endpoint(websocket: WebSocket, scene_id: str) -> None:
    """WebSocket endpoint to stream Redis-based pipeline logs/events to the client."""
    logger.info("New WebSocket connection request for scene_id: %s", scene_id)
    await manager.connect(websocket, scene_id)
    try:
        while True:
            # Maintain connection and respond to client inputs if needed (e.g. ping)
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for scene_id: %s", scene_id)
        manager.disconnect(websocket, scene_id)
    except Exception as e:
        logger.exception("WebSocket error for scene_id %s: %s", scene_id, e)
        manager.disconnect(websocket, scene_id)
