from __future__ import annotations

import logging
from contextvars import ContextVar
from time import perf_counter
from uuid import uuid4

from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
logger = logging.getLogger(__name__)


def get_request_id() -> str | None:
    return request_id_var.get()


def get_request_id_from_request(request: Request) -> str | None:
    return get_request_id() or getattr(request.state, "request_id", None)


class CorrelationIdMiddleware:
    """Pure ASGI middleware preserving request context through error handlers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied = headers.get(b"x-request-id", b"").decode("utf-8", errors="replace").strip()
        request_id = supplied[:128] or str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)
        started = perf_counter()
        response_status = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = int(message["status"])
                response_headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                response_headers.append((b"x-request-id", request_id.encode("utf-8")))
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            duration_ms = (perf_counter() - started) * 1000
            logger.info(
                "HTTP request completed method=%s path=%s status=%d duration_ms=%.2f request_id=%s",
                scope.get("method", ""),
                scope.get("path", ""),
                response_status,
                duration_ms,
                request_id,
            )
            request_id_var.reset(token)
