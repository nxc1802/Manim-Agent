from __future__ import annotations

import uuid

import pytest
from backend.main import app
from fastapi.testclient import TestClient


def test_health_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_ok() -> None:
    client = TestClient(app)
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["redis"] is True


def test_ready_returns_503_when_redis_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import main as main_mod

    def _bad_redis() -> object:
        class _R:
            def ping(self) -> None:
                raise OSError("redis down")

        return _R()

    monkeypatch.setattr(main_mod, "get_redis", _bad_redis)

    client = TestClient(app)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "redis": False}


def test_list_projects_empty() -> None:
    client = TestClient(app)
    response = client.get("/v1/projects")
    assert response.status_code == 200
    assert response.json() == []


def test_project_not_found_stable_json() -> None:
    client = TestClient(app)
    pid = str(uuid.uuid4())
    response = client.get(f"/v1/projects/{pid}")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "http_error"
    assert body["error"]["message"].startswith("Project not found")
    assert body["error"]["request_id"] is not None


def test_invalid_uuid_path_returns_422_stable_json() -> None:
    client = TestClient(app)
    response = client.get("/v1/projects/not-a-uuid")
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "Request validation failed"
    assert "details" in body
    assert body["error"]["request_id"] is not None


def test_correlation_id_roundtrip_header() -> None:
    client = TestClient(app)
    rid = "test-request-id-123"
    response = client.get("/health", headers={"X-Request-ID": rid})
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == rid
