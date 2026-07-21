from app.core.security_headers import SecurityHeadersMiddleware
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(*, enable_hsts: bool) -> TestClient:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=enable_hsts)

    @app.get("/ok")
    def ok() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def test_security_headers_cover_success_and_error_responses() -> None:
    client = _client(enable_hsts=True)

    for response in (client.get("/ok"), client.get("/missing")):
        assert response.headers["content-security-policy"] == (
            "frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
        )
        assert response.headers["permissions-policy"] == (
            "camera=(), microphone=(), geolocation=()"
        )
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["strict-transport-security"] == (
            "max-age=31536000; includeSubDomains"
        )


def test_hsts_is_omitted_for_local_development() -> None:
    response = _client(enable_hsts=False).get("/ok")

    assert "strict-transport-security" not in response.headers
