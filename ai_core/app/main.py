from __future__ import annotations

import hmac
import json
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from shared.schemas.hitl import ChatRequest, ChatResponse

from app.config import settings
from app.llm import GoogleLLM

app = FastAPI(
    title="Manim AI Core",
    version="1.0.0",
    description="Private LLM, streaming and Manim rendering runtime. No database access.",
)


def require_internal_service(x_internal_token: str | None = Header(None)) -> None:
    if not x_internal_token or not hmac.compare_digest(x_internal_token, settings.internal_service_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal service token")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-core"}


@app.post("/internal/chat", response_model=ChatResponse, dependencies=[Depends(require_internal_service)])
def chat(body: ChatRequest) -> ChatResponse:
    model = body.model or settings.default_chat_model
    text = GoogleLLM().complete(
        messages=[message.model_dump() for message in body.messages],
        model=model,
        temperature=0.3,
        max_tokens=4096,
    )
    return ChatResponse(text=text, model=model)


async def _sse_events(body: ChatRequest) -> AsyncIterator[str]:
    model = body.model or settings.default_chat_model
    try:
        async for token in GoogleLLM().stream(
            messages=[message.model_dump() for message in body.messages],
            model=model,
            temperature=0.3,
            max_tokens=4096,
        ):
            yield f"data: {json.dumps({'type': 'delta', 'text': token})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'model': model})}\n\n"
    except Exception as exc:  # noqa: BLE001
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"


@app.post("/internal/chat/stream", dependencies=[Depends(require_internal_service)])
async def stream_chat(body: ChatRequest) -> StreamingResponse:
    return StreamingResponse(_sse_events(body), media_type="text/event-stream")
