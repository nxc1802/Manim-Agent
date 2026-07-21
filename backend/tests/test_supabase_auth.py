from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from app.api.v1.ws import _websocket_token
from app.core import supabase_jwt
from app.core.supabase_jwt import JwtValidationError, user_id_from_supabase_jwt
from app.services import supabase_storage_rest
from app.services.supabase_http import supabase_admin_headers
from cryptography.hazmat.primitives.asymmetric import rsa


def _claims(user_id: str, *, issuer: str) -> dict[str, object]:
    return {
        "sub": user_id,
        "aud": "authenticated",
        "role": "authenticated",
        "iss": issuer,
        "iat": datetime.now(tz=UTC),
        "exp": datetime.now(tz=UTC) + timedelta(minutes=5),
    }


def test_asymmetric_supabase_jwt_is_verified_through_jwks(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    issuer = "https://project.supabase.co/auth/v1"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    user_id = uuid4()
    token = jwt.encode(
        _claims(str(user_id), issuer=issuer),
        private_key,
        algorithm="RS256",
        headers={"kid": "active-key"},
    )

    class Client:
        def get_signing_key_from_jwt(self, supplied: str) -> SimpleNamespace:
            assert supplied == token
            return SimpleNamespace(key=private_key.public_key())

    monkeypatch.setattr(supabase_jwt, "_jwks_client", lambda *_args: Client())

    assert user_id_from_supabase_jwt(
        token,
        secret=None,
        audience="authenticated",
        jwks_url=f"{issuer}/.well-known/jwks.json",
        issuer=issuer,
    ) == user_id


def test_legacy_hs256_requires_explicit_secret() -> None:
    issuer = "https://project.supabase.co/auth/v1"
    token = jwt.encode(
        _claims(str(uuid4()), issuer=issuer),
        "legacy-secret-at-least-thirty-two-bytes",
        algorithm="HS256",
    )

    with pytest.raises(JwtValidationError, match="Legacy HS256"):
        user_id_from_supabase_jwt(
            token,
            secret=None,
            audience="authenticated",
            issuer=issuer,
        )


def test_legacy_hs256_still_supports_controlled_key_rotation() -> None:
    issuer = "https://project.supabase.co/auth/v1"
    user_id = uuid4()
    token = jwt.encode(
        _claims(str(user_id), issuer=issuer),
        "legacy-secret-at-least-thirty-two-bytes",
        algorithm="HS256",
    )

    assert user_id_from_supabase_jwt(
        token,
        secret="legacy-secret-at-least-thirty-two-bytes",
        audience="authenticated",
        issuer=issuer,
    ) == user_id


def test_supabase_admin_headers_do_not_treat_current_secret_key_as_jwt() -> None:
    assert supabase_admin_headers("sb_secret_backend") == {
        "apikey": "sb_secret_backend"
    }
    assert supabase_admin_headers("legacy-service-role") == {
        "apikey": "legacy-service-role",
        "Authorization": "Bearer legacy-service-role",
    }


def test_storage_upload_streams_artifact_without_loading_it_all(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    artifact = tmp_path / "render.mp4"
    artifact.write_bytes(b"video-payload")
    monkeypatch.setattr(supabase_storage_rest.settings, "supabase_url", "https://example.test")
    monkeypatch.setattr(
        supabase_storage_rest.settings,
        "supabase_service_role_key",
        "sb_secret_backend",
    )
    monkeypatch.setattr(supabase_storage_rest.settings, "supabase_storage_bucket", "videos")
    captured: dict[str, object] = {}

    class Response:
        @staticmethod
        def raise_for_status() -> None:
            return None

    def post(url: str, **kwargs):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        captured["body"] = b"".join(kwargs["content"])
        return Response()

    monkeypatch.setattr(supabase_storage_rest.httpx, "post", post)

    assert (
        supabase_storage_rest.upload_render_artifact(
            source_path=artifact,
            object_path="project/render.mp4",
        )
        == "project/render.mp4"
    )
    assert captured["body"] == b"video-payload"
    assert captured["headers"] == {
        "apikey": "sb_secret_backend",
        "x-upsert": "true",
        "Content-Type": "video/mp4",
        "Content-Length": str(len(b"video-payload")),
    }


def test_websocket_bearer_uses_subprotocol_header_instead_of_query_string() -> None:
    class Socket:
        headers = {"sec-websocket-protocol": "manim.jwt, header.jwt.token"}
        query_params = {"token": "query.jwt.must-not-be-used"}

    assert _websocket_token(Socket()) == ("header.jwt.token", "manim.jwt")  # type: ignore[arg-type]
