from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings


def get_user_id_key(request: Any) -> str:
    # Try to get user_id from request state if it was set by auth middleware/dep
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return str(user_id)
    return str(get_remote_address(request))


limiter = Limiter(key_func=get_user_id_key)


def increment_user_token_usage(user_id: UUID, tokens: int) -> None:
    """Increment token consumption for a user on the current day with 36-hour expiration."""
    import time

    from app.services.redis_client import get_redis

    redis = get_redis()
    day_str = time.strftime("%Y-%m-%d")
    key = f"{settings.redis_prefix}:user_tokens:{user_id}:{day_str}"
    try:
        pipe = redis.pipeline()
        pipe.incrby(key, tokens)
        pipe.expire(key, 36 * 3600)
        pipe.execute()
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning("Failed to update user token usage: %s", e)


def check_user_token_budget(user_id: UUID, max_tokens_per_day: int = 100_000) -> bool:
    """Check if the user is within their daily token budget."""
    import time

    from app.services.redis_client import get_redis

    redis = get_redis()
    day_str = time.strftime("%Y-%m-%d")
    key = f"{settings.redis_prefix}:user_tokens:{user_id}:{day_str}"
    try:
        used = redis.get(key)
        if used is None:
            return True
        return int(cast(Any, used)) < max_tokens_per_day
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning("Failed to check user token budget: %s", e)
        return True
