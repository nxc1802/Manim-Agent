from __future__ import annotations

import json
from uuid import UUID

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from shared.schemas.hitl import ChatRequest

from app.core.config import settings
from app.core.supabase_jwt import JwtValidationError, user_id_from_supabase_jwt
from app.core.websocket_manager import manager
from app.db.content_store import get_content_store

router = APIRouter()


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
        await websocket.close(code=4404, reason="Project not found")
        return
    await manager.connect(websocket, str(project_id))
    try:
        while True:
            if await websocket.receive_text() == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, str(project_id))


@router.websocket("/ws/chat")
async def streaming_chat(websocket: WebSocket) -> None:
    """Relay AI Core's SSE token stream onto an authenticated WebSocket."""
    if _websocket_user_id(websocket) is None:
        await websocket.close(code=4401, reason="Unauthorized")
        return
    await websocket.accept()
    try:
        while True:
            request = ChatRequest.model_validate(json.loads(await websocket.receive_text()))
            async with httpx.AsyncClient(timeout=180.0) as client:
                async with client.stream(
                    "POST",
                    f"{settings.ai_core_url.rstrip('/')}/internal/chat/stream",
                    headers={"X-Internal-Token": settings.internal_service_token},
                    json=request.model_dump(mode="json"),
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            await websocket.send_text(line.removeprefix("data: "))
    except (WebSocketDisconnect, httpx.HTTPError):
        await websocket.close()
    except Exception as exc:  # noqa: BLE001
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close(code=1011)
