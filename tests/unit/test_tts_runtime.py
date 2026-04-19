from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from ai_engine.piper_config import PiperRuntimeConfig
from backend.core.config import settings
from backend.services.content_store import RedisContentStore
from backend.services.redis_client import get_redis
from backend.services.voice_job_store import RedisVoiceJobStore
from worker.tts_runtime import _audio_duration_seconds, _write_silent_wav, execute_voice_job
from worker.tts_tasks import synthesize_voice


def test_execute_voice_job_piper_updates_scene_and_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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

    def _fake_piper(_cfg: object, _text: str, out_wav: Path) -> None:
        _write_silent_wav(out_wav, 0.6)

    monkeypatch.setattr("worker.tts_runtime._run_piper", _fake_piper)
    project_id = uuid4()
    scene_id = uuid4()
    job_id = uuid4()
    store = RedisContentStore(get_redis())
    vstore = RedisVoiceJobStore(get_redis())
    store.create_project(
        project_id=project_id,
        user_id=settings.dev_default_user_id,
        title="tts-test",
        description=None,
        source_language="vi",
    )
    store.create_scene(
        scene_id=scene_id,
        project_id=project_id,
        scene_order=0,
        storyboard_status="approved",
    )
    vstore.create_queued_job(
        job_id=job_id,
        project_id=project_id,
        scene_id=scene_id,
        metadata={"synthesis_text": "hello there world"},
    )
    execute_voice_job(job_id)
    job = vstore.get(job_id)
    assert job is not None
    assert job.status == "completed"
    assert job.asset_url
    assert job.metadata.get("granularity") == "segment"
    scene = store.get_scene(scene_id)
    assert scene is not None
    assert scene.audio_url
    assert scene.timestamps is not None
    assert scene.timestamps.get("version") == "2"
    assert scene.timestamps.get("segments")


def test_synthesize_voice_task_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    m = MagicMock()
    monkeypatch.setattr("worker.tts_runtime.execute_voice_job", m)
    jid = str(uuid4())
    synthesize_voice(jid)
    m.assert_called_once()


def test_audio_duration_fallback_to_wav_header(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_: object) -> float:
        raise RuntimeError("no ffprobe")

    monkeypatch.setattr("worker.tts_runtime._ffprobe_duration_seconds", boom)
    p = tmp_path / "x.wav"
    _write_silent_wav(p, 0.5)
    d = _audio_duration_seconds(p)
    assert 0.45 < d < 0.55
