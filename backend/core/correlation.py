from __future__ import annotations

import contextvars
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id",
    default=None,
)


def get_request_id() -> str | None:
    return request_id_ctx.get()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Propagate `X-Request-ID` (generate if missing) for tracing and error payloads."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        header_rid = request.headers.get("x-request-id")
        rid = (header_rid.strip() if header_rid else "") or str(uuid.uuid4())
        
        # Propagate to both standard request context and pipeline trace context
        token_rid = request_id_ctx.set(rid)
        from shared.pipeline_log import pipeline_trace_id_var
        token_trace = pipeline_trace_id_var.set(rid)
        
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token_rid)
            pipeline_trace_id_var.reset(token_trace)
        response.headers["X-Request-ID"] = rid
        return response
