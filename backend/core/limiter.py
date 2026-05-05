from __future__ import annotations
from slowapi import Limiter
from slowapi.util import get_remote_address

def get_user_id_key(request) -> str:
    # Try to get user_id from request state if it was set by auth middleware/dep
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return str(user_id)
    return get_remote_address(request)

limiter = Limiter(key_func=get_user_id_key)
