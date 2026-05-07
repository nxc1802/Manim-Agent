from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from backend.core.config import settings
from backend.core.correlation import get_request_id

logger = logging.getLogger(__name__)

class AppException(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Any | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)

# RFC 9110 name; Python 3.13+ exposes `UNPROCESSABLE_CONTENT` (422).
_VALIDATION_STATUS = getattr(HTTPStatus, "UNPROCESSABLE_CONTENT", HTTPStatus.UNPROCESSABLE_ENTITY)


def _error_payload(
    *,
    code: str,
    message: str,
    request_id: str | None,
    details: Any | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        },
    }
    if details is not None:
        body["details"] = jsonable_encoder(details)
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        rid = get_request_id()
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(
                code=exc.code,
                message=exc.message,
                request_id=rid,
                details=exc.details,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        rid = get_request_id()
        detail = exc.detail
        if isinstance(detail, str):
            message = detail
        elif isinstance(detail, list):
            message = "Request failed"
        else:
            message = str(detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(
                code="http_error",
                message=message,
                request_id=rid,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        rid = get_request_id()
        return JSONResponse(
            status_code=_VALIDATION_STATUS,
            content=_error_payload(
                code="validation_error",
                message="Request validation failed",
                request_id=rid,
                details=exc.errors(),
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        rid = get_request_id()
        logger.exception("Unhandled error (request_id=%s)", rid)
        if settings.app_env == "production":
            message = "Internal server error"
        else:
            message = str(exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_payload(
                code="internal_error",
                message=message,
                request_id=rid,
            ),
        )
