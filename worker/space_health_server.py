"""Tiny HTTP server so Hugging Face Docker Spaces can pass port health checks.

Celery workers do not open a port; HF expects something to listen on ``PORT`` (default 7860).
Run this in the background alongside ``celery worker`` (see docker/*/entrypoint.sh).
"""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"ok\n")


def main() -> None:
    port = int(os.environ.get("PORT", "7860"))
    HTTPServer(("0.0.0.0", port), _Handler).serve_forever()


if __name__ == "__main__":
    main()
