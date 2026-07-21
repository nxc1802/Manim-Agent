from __future__ import annotations

import logging
import os
from os import PathLike, stat_result
from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

logger = logging.getLogger(__name__)

_RESERVED_PREFIXES = (
    "/v1",
    "/internal",
    "/health",
    "/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
)


def _is_reserved_application_path(path: str) -> bool:
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in _RESERVED_PREFIXES)


class SpaStaticFiles(StaticFiles):
    """Serve immutable Vite assets and fall back to the SPA entry document.

    Unknown API, health, internal, and documentation routes retain a real 404;
    only extensionless browser routes are eligible for the React fallback.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            request_path = str(scope.get("path") or "/")
            is_browser_route = (
                exc.status_code == 404
                and scope.get("method") in {"GET", "HEAD"}
                and not Path(path).suffix
                and not _is_reserved_application_path(request_path)
            )
            if not is_browser_route:
                raise
            return await super().get_response("index.html", scope)

    def file_response(
        self,
        full_path: PathLike[str],
        stat_result: stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        normalized = str(full_path).replace(os.sep, "/")
        if normalized.endswith("/index.html"):
            response.headers["Cache-Control"] = "no-cache"
        elif "/assets/" in normalized:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def mount_static_spa(app: FastAPI, directory: str | Path | None = None) -> bool:
    """Mount a built frontend when present and remain a pure API otherwise."""

    configured = directory or os.getenv("SPA_STATIC_DIR")
    if configured is None:
        logger.info("SPA_STATIC_DIR is unset; running in API-only mode")
        return False
    static_dir = Path(configured).expanduser().resolve()
    if not (static_dir / "index.html").is_file():
        logger.info("SPA build not found; API-only mode static_dir=%s", static_dir)
        return False
    app.mount("/", SpaStaticFiles(directory=static_dir, html=True), name="spa")
    logger.info("SPA mounted static_dir=%s", static_dir)
    return True
