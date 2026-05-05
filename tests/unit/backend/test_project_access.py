from __future__ import annotations

from typing import Generator
from uuid import UUID, uuid4

import pytest
from backend.api.deps import get_request_user_id
from backend.core.config import settings
from backend.main import app
from backend.services.redis_client import configure_redis
from fakeredis import FakeRedis
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    configure_redis(FakeRedis(decode_responses=True))
    with TestClient(app) as c:
        yield c


def test_get_project_returns_404_for_non_owner(client: TestClient) -> None:
    other = uuid4()

    def as_owner() -> UUID:
        return settings.dev_default_user_id

    app.dependency_overrides[get_request_user_id] = as_owner
    try:
        r0 = client.post("/v1/projects", json={"title": "Secret", "source_language": "vi"})
        assert r0.status_code == 201
        project_id = r0.json()["id"]
    finally:
        app.dependency_overrides.clear()

    app.dependency_overrides[get_request_user_id] = lambda: other
    try:
        r1 = client.get(f"/v1/projects/{project_id}")
        assert r1.status_code == 404
    finally:
        app.dependency_overrides.clear()
