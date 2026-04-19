from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from ai_engine.llm_client import FakeLLMClient
from ai_engine.piper_config import PiperRuntimeConfig
from backend.api.deps import get_llm_client
from backend.main import app
from backend.services.content_store import RedisContentStore
from backend.services.redis_client import configure_redis, get_redis
from fakeredis import FakeRedis
from fastapi.testclient import TestClient
from worker.tts_runtime import _write_silent_wav, execute_voice_job


@pytest.fixture()
def api_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    onnx = tmp_path / "voice.onnx"
    onnx.write_bytes(b"fake")
    cfg = PiperRuntimeConfig(
        binary=sys.executable,
        voice_model_path=str(onnx),
        noise_scale=0.667,
        length_scale=1.0,
        sentence_silence=0.25,
    )
    monkeypatch.setattr("worker.tts_runtime.load_piper_runtime_config", lambda: cfg)

    def _fake_piper(_cfg: PiperRuntimeConfig, _text: str, out_wav: Path) -> None:
        _write_silent_wav(out_wav, 0.8)

    monkeypatch.setattr("worker.tts_runtime._run_piper", _fake_piper)
    configure_redis(FakeRedis(decode_responses=True))
    fixture_json = Path(__file__).resolve().parents[1] / "fixtures" / "planner_output_valid.json"
    planner_json = fixture_json.read_text(encoding="utf-8")
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient(planner_json=planner_json)
    mock_task = MagicMock()

    def _run(jid: str) -> None:
        execute_voice_job(UUID(jid))

    mock_task.delay.side_effect = _run
    monkeypatch.setattr("backend.api.v1.scenes.synthesize_voice", mock_task)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _bootstrap_approved_scene(client: TestClient) -> tuple[UUID, UUID]:
    r0 = client.post("/v1/projects", json={"title": "Voice", "source_language": "vi"})
    assert r0.status_code == 201, r0.text
    project_id = UUID(r0.json()["id"])
    r1 = client.post(f"/v1/projects/{project_id}/scenes", json={"scene_order": 0})
    assert r1.status_code == 201, r1.text
    scene_id = UUID(r1.json()["id"])
    assert client.post(f"/v1/scenes/{scene_id}/generate-storyboard", json={}).status_code == 200
    assert client.post(f"/v1/scenes/{scene_id}/approve-storyboard").status_code == 200
    return project_id, scene_id


def test_voice_enqueue_completes_and_updates_scene(api_client: TestClient) -> None:
    project_id, scene_id = _bootstrap_approved_scene(api_client)
    r = api_client.post(f"/v1/scenes/{scene_id}/voice", json={})
    assert r.status_code == 202, r.text
    voice_job_id = UUID(r.json()["voice_job_id"])
    jr = api_client.get(f"/v1/voice-jobs/{voice_job_id}")
    assert jr.status_code == 200, jr.text
    assert jr.json()["status"] == "completed"
    assert jr.json()["asset_url"]
    meta = jr.json()["metadata"]
    assert meta["granularity"] == "segment"
    assert meta["timestamps"]["version"] == "2"

    scenes = api_client.get(f"/v1/projects/{project_id}/scenes")
    assert scenes.status_code == 200
    body = scenes.json()
    assert len(body) == 1
    sc = body[0]
    assert sc["id"] == str(scene_id)
    assert sc["audio_url"]
    assert sc["timestamps"]["version"] == "2"
    assert sc["timestamps"]["segments"]


def test_voice_requires_approved_storyboard(api_client: TestClient) -> None:
    r0 = api_client.post("/v1/projects", json={"title": "V2", "source_language": "vi"})
    project_id = UUID(r0.json()["id"])
    r1 = api_client.post(f"/v1/projects/{project_id}/scenes", json={"scene_order": 0})
    scene_id = UUID(r1.json()["id"])
    r2 = api_client.post(f"/v1/scenes/{scene_id}/voice", json={})
    assert r2.status_code == 400
    msg = r2.json()["error"]["message"].lower()
    assert "approved" in msg


def test_voice_no_script_returns_400(api_client: TestClient) -> None:
    _project_id, scene_id = _bootstrap_approved_scene(api_client)
    store = RedisContentStore(get_redis())
    updated = store.update_scene(
        scene_id,
        storyboard_text="",
        voice_script=None,
        storyboard_status="approved",
    )
    assert updated is not None
    r = api_client.post(f"/v1/scenes/{scene_id}/voice", json={})
    assert r.status_code == 400


def test_voice_override_persisted_on_scene(api_client: TestClient) -> None:
    project_id, scene_id = _bootstrap_approved_scene(api_client)
    r = api_client.post(
        f"/v1/scenes/{scene_id}/voice",
        json={"voice_script_override": "First block.\n\nSecond block here."},
    )
    assert r.status_code == 202, r.text
    voice_job_id = UUID(r.json()["voice_job_id"])
    assert api_client.get(f"/v1/voice-jobs/{voice_job_id}").json()["status"] == "completed"
    scenes = api_client.get(f"/v1/projects/{project_id}/scenes").json()
    sc = scenes[0]
    assert sc["voice_script"] == "First block.\n\nSecond block here."
    segs = sc["timestamps"]["segments"]
    assert len(segs) == 2
