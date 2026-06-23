from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.config import settings
from backend.core.supabase_jwt import JwtValidationError, user_id_from_supabase_jwt
from backend.core.websocket_manager import manager
from backend.db.content_store import get_content_store

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/{scene_id}")
async def websocket_endpoint(websocket: WebSocket, scene_id: str) -> None:
    """WebSocket endpoint to stream Redis-based pipeline logs/events to the client."""
    try:
        sid = UUID(scene_id)
    except ValueError:
        await websocket.close(code=4400, reason="Invalid scene id")
        return

    if settings.auth_mode == "jwt":
        token = websocket.query_params.get("token")
        if not token:
            auth_header = websocket.headers.get("authorization", "")
            if auth_header.lower().startswith("bearer "):
                token = auth_header[7:].strip()
        secret = (settings.supabase_jwt_secret or "").strip()
        try:
            if not token or not secret:
                raise JwtValidationError("Missing WebSocket credentials")
            user_id = user_id_from_supabase_jwt(
                token,
                secret=secret,
                audience=(settings.supabase_jwt_audience or "").strip() or None,
            )
        except JwtValidationError:
            await websocket.close(code=4401, reason="Unauthorized")
            return
    else:
        user_id = settings.dev_default_user_id

    store = get_content_store()
    scene = store.get_scene(sid)
    project = store.get_project(scene.project_id) if scene else None
    if scene is None or project is None or project.user_id != user_id:
        await websocket.close(code=4404, reason="Scene not found")
        return

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
