from __future__ import annotations

from uuid import UUID

import jwt
import pytest
from backend.core.supabase_jwt import JwtValidationError, user_id_from_supabase_jwt


def test_user_id_from_valid_jwt() -> None:
    secret = "unit-test-secret-at-least-32-chars-long!!"
    uid = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    token = jwt.encode(
        {"sub": str(uid), "aud": "authenticated"},
        secret,
        algorithm="HS256",
    )
    out = user_id_from_supabase_jwt(
        token,
        secret=secret,
        audience="authenticated",
    )
    assert out == uid


def test_user_id_rejects_bad_signature() -> None:
    secret_a = "unit-test-secret-at-least-32-chars-long!!"
    secret_b = "other-test-secret-at-least-32-chars-long!"
    token = jwt.encode(
        {"sub": str(UUID(int=1)), "aud": "authenticated"},
        secret_a,
        algorithm="HS256",
    )
    with pytest.raises(JwtValidationError):
        user_id_from_supabase_jwt(token, secret=secret_b, audience="authenticated")
