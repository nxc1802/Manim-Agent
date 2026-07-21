from __future__ import annotations

from functools import lru_cache
from uuid import UUID

import jwt
from jwt import InvalidTokenError, PyJWKClient, PyJWKClientError


class JwtValidationError(ValueError):
    """Raised when a Supabase-style JWT cannot be validated."""


def user_id_from_supabase_jwt(
    token: str,
    *,
    secret: str | None,
    audience: str | None,
    jwks_url: str | None = None,
    issuer: str | None = None,
    jwks_cache_seconds: int = 300,
) -> UUID:
    """Verify a Supabase access token and return its UUID ``sub`` claim.

    Asymmetric Supabase signing keys are resolved from the project's JWKS.
    HS256 is accepted only when an explicit legacy JWT secret is configured.
    """
    try:
        header = jwt.get_unverified_header(token)
        algorithm = str(header.get("alg") or "")
        if algorithm in {"ES256", "RS256"}:
            if not jwks_url:
                raise JwtValidationError("JWT key discovery is not configured")
            signing_key = _jwks_client(jwks_url, jwks_cache_seconds).get_signing_key_from_jwt(
                token
            )
            key = signing_key.key
        elif algorithm == "HS256":
            if not secret or not secret.strip():
                raise JwtValidationError("Legacy HS256 JWT validation is not configured")
            key = secret.strip()
        else:
            raise JwtValidationError("JWT signing algorithm is not allowed")

        options = {
            "verify_aud": bool(audience),
            "verify_iss": bool(issuer),
            "require": ["exp", "sub"],
        }
        if audience:
            payload = jwt.decode(
                token,
                key,
                algorithms=[algorithm],
                audience=audience,
                issuer=issuer,
                options=options,
            )
        else:
            payload = jwt.decode(
                token,
                key,
                algorithms=[algorithm],
                issuer=issuer,
                options=options,
            )
    except JwtValidationError:
        raise
    except (InvalidTokenError, PyJWKClientError, OSError) as exc:
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


@lru_cache(maxsize=8)
def _jwks_client(url: str, cache_seconds: int) -> PyJWKClient:
    """Cache public key sets for less than Supabase Edge's ten-minute TTL."""
    return PyJWKClient(
        url,
        cache_keys=True,
        max_cached_keys=16,
        cache_jwk_set=True,
        lifespan=cache_seconds,
        timeout=5,
    )
