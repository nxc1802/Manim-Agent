from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websockets"])

@router.websocket("/ws/{scene_id}")
async def scene_status_websocket(websocket: WebSocket, scene_id: UUID):
    sid_str = str(scene_id)
    await manager.connect(websocket, sid_str)
    try:
        # Keep connection open and handle incoming messages if any (heartbeats, etc.)
        while True:
            data = await websocket.receive_text()
            # We don't expect much from client, but we can echo or handle ping/pong
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, sid_str)
        logger.info(f"WebSocket disconnected for scene: {sid_str}")
    except Exception:
        manager.disconnect(websocket, sid_str)
        logger.exception(f"WebSocket error for scene: {sid_str}")
