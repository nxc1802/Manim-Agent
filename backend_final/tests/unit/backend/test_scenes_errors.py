from __future__ import annotations

from collections.abc import Generator
from uuid import uuid4

import pytest
from backend.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


def test_get_scene_404(client: TestClient) -> None:
    r = client.get(f"/v1/scenes/{uuid4()}")
    assert r.status_code == 404


def test_generate_storyboard_404(client: TestClient) -> None:
    r = client.post(f"/v1/scenes/{uuid4()}/generate-storyboard")
    assert r.status_code == 404


def test_approve_storyboard_404(client: TestClient) -> None:
    r = client.post(f"/v1/scenes/{uuid4()}/approve-storyboard")
    assert r.status_code == 404


def test_run_scene_planner_404(client: TestClient) -> None:
    r = client.post(f"/v1/scenes/{uuid4()}/plan")
    assert r.status_code == 404


def test_approve_plan_404(client: TestClient) -> None:
    r = client.post(f"/v1/scenes/{uuid4()}/approve-plan")
    assert r.status_code == 404


def test_approve_voice_script_404(client: TestClient) -> None:
    r = client.post(f"/v1/scenes/{uuid4()}/approve-voice-script")
    assert r.status_code == 404


def test_sync_timeline_404(client: TestClient) -> None:
    r = client.post(f"/v1/scenes/{uuid4()}/sync-timeline")
    assert r.status_code == 404


def test_generate_code_404(client: TestClient) -> None:
    r = client.post(f"/v1/scenes/{uuid4()}/generate-code")
    assert r.status_code == 404


def test_review_round_404(client: TestClient) -> None:
    r = client.post(f"/v1/scenes/{uuid4()}/review-round")
    assert r.status_code == 404


def test_run_review_loop_404(client: TestClient) -> None:
    r = client.post(f"/v1/scenes/{uuid4()}/run-review-loop")
    assert r.status_code == 404


def test_hitl_ack_404(client: TestClient) -> None:
    r = client.post(f"/v1/scenes/{uuid4()}/hitl-ack-builder-review", json={"action": "stop"})
    assert r.status_code == 404
