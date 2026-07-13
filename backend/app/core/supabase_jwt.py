from __future__ import annotations

from uuid import UUID

import jwt
from jwt import InvalidTokenError


class JwtValidationError(ValueError):
    """Raised when a Supabase-style JWT cannot be validated."""


def user_id_from_supabase_jwt(
    token: str,
    *,
    secret: str,
    audience: str | None,
) -> UUID:
    """Decode HS256 JWT and return `sub` as UUID (Supabase Auth user id)."""
    try:
        if audience:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience=audience,
            )
        else:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
    except InvalidTokenError as exc:
        msg = "Invalid or expired token"
        raise JwtValidationError(msg) from exc
    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub.strip():
        msg = "Token missing sub claim"
        raise JwtValidationError(msg)
    try:
        return UUID(sub)
    except ValueError as exc:
        msg = "Token sub is not a valid UUID"
        raise JwtValidationError(msg) from exc
