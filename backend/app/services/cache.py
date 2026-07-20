from __future__ import annotations

import json
import logging
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

# A real cached JSON ``null`` must be distinguishable from a cache miss.
CACHE_MISS = object()


class RedisJsonCache:
    """Small fail-open JSON cache shared by Backend persistence adapters.

    Supabase remains the source of truth. Redis failures are logged and treated
    as misses so a cache incident never makes otherwise healthy database reads
    unavailable.
    """

    def __init__(self, client: Redis) -> None:
        self._redis = client

    @staticmethod
    def key(*parts: object) -> str:
        suffix = ":".join(str(part) for part in parts)
        return f"{settings.redis_prefix}:cache:{suffix}"

    def get(self, key: str) -> Any:
        if not settings.cache_enabled:
            return CACHE_MISS
        try:
            raw = self._redis.get(key)
            if raw is None:
                return CACHE_MISS
            payload = json.loads(str(raw))
            if not isinstance(payload, dict) or "value" not in payload:
                self._redis.delete(key)
                return CACHE_MISS
            return payload["value"]
        except (RedisError, TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Cache read failed key=%s error=%s", key, exc)
            return CACHE_MISS

    def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        if not settings.cache_enabled:
            return
        ttl = ttl_seconds
        if ttl is None:
            ttl = (
                settings.cache_negative_ttl_seconds
                if value is None
                else settings.cache_ttl_seconds
            )
        try:
            self._redis.setex(
                key,
                ttl,
                json.dumps({"value": value}, default=str, separators=(",", ":")),
            )
        except (RedisError, TypeError, ValueError) as exc:
            logger.warning("Cache write failed key=%s error=%s", key, exc)

    def delete(self, *keys: str) -> None:
        if not settings.cache_enabled or not keys:
            return
        try:
            self._redis.delete(*keys)
        except RedisError as exc:
            logger.warning("Cache invalidation failed keys=%s error=%s", keys, exc)

    def generation(self, scope: str) -> int:
        if not settings.cache_enabled:
            return 0
        key = self.key("generation", scope)
        try:
            raw = self._redis.get(key)
            return int(raw) if raw is not None else 0
        except (RedisError, TypeError, ValueError) as exc:
            logger.warning("Cache generation read failed scope=%s error=%s", scope, exc)
            return 0

    def bump(self, *scopes: str) -> None:
        if not settings.cache_enabled or not scopes:
            return
        try:
            pipe = self._redis.pipeline(transaction=False)
            for scope in scopes:
                key = self.key("generation", scope)
                pipe.incr(key)
                # Generation counters can outlive data briefly, but not forever.
                pipe.expire(key, settings.cache_generation_ttl_seconds)
            pipe.execute()
        except RedisError as exc:
            logger.warning("Cache generation bump failed scopes=%s error=%s", scopes, exc)
