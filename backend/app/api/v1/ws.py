from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.supabase_jwt import JwtValidationError, user_id_from_supabase_jwt
from app.core.websocket_manager import manager
from app.db.content_store import get_content_store

router = APIRouter()
logger = logging.getLogger(__name__)


def _websocket_user_id(websocket: WebSocket) -> UUID | None:
    if settings.auth_mode != "jwt":
        return settings.dev_default_user_id
    token = websocket.query_params.get("token")
    if not token:
        header = websocket.headers.get("authorization", "")
        token = header[7:].strip() if header.lower().startswith("bearer ") else None
    try:
        if not token or not settings.supabase_jwt_secret:
            return None
        return user_id_from_supabase_jwt(
            token,
            secret=settings.supabase_jwt_secret,
            audience=(settings.supabase_jwt_audience or "").strip() or None,
        )
    except JwtValidationError:
        return None


@router.websocket("/ws/projects/{project_id}")
async def project_events(websocket: WebSocket, project_id: UUID) -> None:
    user_id = _websocket_user_id(websocket)
    project = get_content_store().get_project(project_id)
    if user_id is None or project is None or project.user_id != user_id:
        logger.warning("WebSocket authorization rejected project_id=%s", project_id)
        await websocket.close(code=4404, reason="Project not found")
        return
    await manager.connect(websocket, str(project_id))
    try:
        while True:
            if await websocket.receive_text() == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("WebSocket receive loop failed project_id=%s", project_id)
    finally:
        await manager.disconnect(websocket, str(project_id))
