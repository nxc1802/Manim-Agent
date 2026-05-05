from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from backend.api.access import project_readable_by_user
from backend.api.deps import get_content_store, get_request_user_id
from backend.core.websocket_manager import manager
from backend.db.base import ContentStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websockets"])

@router.websocket("/ws/{scene_id}")
async def scene_status_websocket(
    websocket: WebSocket,
    scene_id: UUID,
    token: str | None = Query(None),
    store: ContentStore = Depends(get_content_store),
):
    sid_str = str(scene_id)
    
    # 1. Authenticate
    try:
        # We manually call dependency logic since @limiter or other decorators might not work on WS as expected
        # For WS, we accept token in query param or standard Bearer header
        from fastapi.security import HTTPAuthorizationCredentials
        auth_creds = None
        if token:
            auth_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        else:
            # Try to get from headers
            auth_header = websocket.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                auth_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=auth_header[7:])
        
        user_id = get_request_user_id(auth_creds)
    except Exception as e:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=str(e))
        return

    # 2. Authorize (Scene Ownership)
    scene = store.get_scene(scene_id)
    if not scene:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Scene not found")
        return
        
    try:
        project_readable_by_user(store, scene.project_id, user_id)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Access denied")
        return

    await manager.connect(websocket, sid_str)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, sid_str)
        logger.info(f"WebSocket disconnected for scene: {sid_str}")
    except Exception:
        manager.disconnect(websocket, sid_str)
        logger.exception(f"WebSocket error for scene: {sid_str}")
