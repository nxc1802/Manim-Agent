from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from redis import Redis

_client: Redis | None = None


def get_redis() -> Redis:
    """Shared Redis sync client (API + in-process tests can override via `configure_redis`)."""
    global _client
    if _client is None:
        from redis import Redis as RedisCls

        _client = RedisCls.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=settings.redis_max_connections,
        )
    return _client


def configure_redis(client: Redis | None) -> None:
    """Test hook: set a custom client (e.g. `fakeredis`) or reset to lazy default."""
    global _client
    _client = client


def close_redis() -> None:
    """Close and reset the process-wide sync Redis pool during app shutdown."""
    global _client
    client = _client
    _client = None
    if client is not None:
        client.close()
