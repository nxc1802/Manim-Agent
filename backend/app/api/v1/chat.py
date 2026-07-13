from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from shared.schemas.hitl import ChatRequest, ChatResponse

from app.api.deps import get_request_user_id
from app.core.config import settings

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse, summary="Fast synchronous chat")
async def chat(
    body: ChatRequest,
    _user_id=Depends(get_request_user_id),  # noqa: B008
) -> ChatResponse:
    """A transport-only proxy; LLM selection and inference stay in AI Core."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.ai_core_url.rstrip('/')}/internal/chat",
                headers={"X-Internal-Token": settings.internal_service_token},
                json=body.model_dump(mode="json"),
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI Core unavailable") from exc
    return ChatResponse.model_validate(response.json())
