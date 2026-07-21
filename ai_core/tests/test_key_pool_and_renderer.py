from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from app.config import Settings
from app.llm import GoogleAPIKeyPool, GoogleLLM, KeyState
from app.renderer import (
    ManimProcessTimeout,
    UnsafeManimCode,
    _mux_audio,
    _run_manim,
    _sanitized_subprocess_env,
    validate_manim_code,
)
from app.tts import synthesize_speech


def test_google_key_enters_cooldown_and_next_key_is_selected() -> None:
    pool = GoogleAPIKeyPool(["key-a", "key-b"])
    key, identity = pool.acquire()
    assert key == "key-a"
    pool.record_failure(identity, RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded"))
    next_key, _ = pool.acquire()
    assert next_key == "key-b"
    assert pool.snapshot()[0]["state"] == KeyState.COOLDOWN


def test_google_key_daily_quota_is_exhausted_until_next_day() -> None:
    pool = GoogleAPIKeyPool(["key-a"])
    _, identity = pool.acquire()
    pool.record_failure(identity, RuntimeError("RequestsPerDay quota exceeded"))
    assert pool.snapshot()[0]["state"] == KeyState.EXHAUSTED
    with pytest.raises(RuntimeError, match="No AVAILABLE"):
        pool.acquire()


def test_google_key_value_is_never_used_as_state_key() -> None:
    pool = GoogleAPIKeyPool(["super-secret-provider-key"])

    pool.acquire()

    stored_keys = set(pool._redis._hashes)  # type: ignore[attr-defined]
    assert stored_keys
    assert all("super-secret-provider-key" not in key for key in stored_keys)


def test_provider_failures_redact_api_keys_from_logs_and_task_errors(
    monkeypatch, caplog
) -> None:  # type: ignore[no-untyped-def]
    import app.llm as llm_module

    secret = "super-secret-provider-key"
    pool = GoogleAPIKeyPool([secret])
    client = GoogleLLM(pool)

    def fail_completion(**_kwargs):  # noqa: ANN202
        raise RuntimeError(f"provider rejected credential {secret}")

    monkeypatch.setattr(llm_module, "completion", fail_completion)
    with pytest.raises(RuntimeError, match="Google provider request failed") as error:
        client.complete(
            messages=[{"role": "user", "content": "test"}],
            model="gemini-3-flash-preview",
            temperature=0.1,
            max_tokens=32,
        )

    assert secret not in str(error.value)
    assert secret not in caplog.text
    assert "[REDACTED]" in str(error.value)


def test_production_ai_settings_require_a_provider_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "INTERNAL_SERVICE_TOKEN", "a-production-internal-token-with-32-characters"
    )
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    for name in tuple(os.environ):
        if name.startswith("GOOGLE_API_KEY_"):
            monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValueError, match="Google provider key"):
        Settings(_env_file=None)

    monkeypatch.setenv("GOOGLE_API_KEY_2", "provider-key-with-a-numbering-gap")
    assert Settings(_env_file=None).app_env == "production"


def test_renderer_rejects_unsafe_import_before_subprocess() -> None:
    with pytest.raises(UnsafeManimCode, match="Import is not allowed"):
        validate_manim_code("import os\nfrom manim import Scene\n")


def test_renderer_rejects_reflection_import_bypass() -> None:
    bypass = "imp = getattr(__builtins__, '__import__')\nos = imp('os')\n"
    with pytest.raises(UnsafeManimCode, match="not allowed"):
        validate_manim_code(bypass)


@pytest.mark.parametrize(
    "bypass",
    [
        "import numpy as np\npayload = np.fromfile('/proc/1/environ')",
        "import numpy as np\npayload = np.load('../../data/redis/appendonly.aof')",
        "from numpy import memmap\npayload = memmap('/etc/passwd')",
        "from manim import *\nlabel = Text('https://169.254.169.254/latest/meta-data')",
        "from manim import *\nimage = ImageMobject('/data/redis/appendonly.aof')",
    ],
)
def test_renderer_rejects_file_and_network_resource_bypasses(bypass: str) -> None:
    with pytest.raises(UnsafeManimCode, match="not allowed"):
        validate_manim_code(bypass)


def test_renderer_subprocess_environment_drops_service_secrets(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "secret")
    monkeypatch.setenv("GOOGLE_API_KEY", "secret")
    monkeypatch.setenv("PATH", "/safe/bin")

    child_env = _sanitized_subprocess_env(tmp_path)

    assert child_env["PATH"] == "/safe/bin"
    assert child_env["HOME"] == str(tmp_path)
    assert "INTERNAL_SERVICE_TOKEN" not in child_env
    assert "GOOGLE_API_KEY" not in child_env


def test_tts_sends_the_configured_voice_and_writes_mp3(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from unittest.mock import MagicMock

    import app.tts as tts

    monkeypatch.setattr(tts, "configured_google_keys", lambda: ["test-key"])
    response = MagicMock()
    response.json.return_value = {"audioContent": "bXAz"}
    response.raise_for_status.return_value = None
    request = MagicMock(return_value=response)
    monkeypatch.setattr(tts.httpx, "post", request)

    audio = synthesize_speech(
        narration="Xin chào",
        source_language="vi",
        user_settings={
            "tts_enabled": True,
            "tts_voice": "vi-VN-Standard-A",
            "tts_speaking_rate": 1.25,
            "tts_pitch": 2,
        },
        destination=tmp_path / "voice.mp3",
    )

    assert audio and audio.read_bytes() == b"mp3"
    payload = request.call_args.kwargs["json"]
    assert request.call_args.kwargs["headers"] == {"x-goog-api-key": "test-key"}
    assert "params" not in request.call_args.kwargs
    assert payload["voice"] == {"languageCode": "vi-VN", "name": "vi-VN-Standard-A"}
    assert payload["audioConfig"]["audioEncoding"] == "MP3"


def test_audio_mux_pads_the_shorter_stream_and_maps_video_and_audio(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    from subprocess import CompletedProcess

    import app.renderer as renderer

    monkeypatch.setattr(renderer, "_probe_duration", lambda file, _work_dir: 4 if file.suffix == ".mp4" else 6)

    def fake_run(command, **_kwargs):  # type: ignore[no-untyped-def]
        Path(command[-1]).touch()
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(renderer.subprocess, "run", fake_run)
    destination = tmp_path / "with_audio.mp4"
    _mux_audio(
        video_file=tmp_path / "scene.mp4",
        audio_file=tmp_path / "voice.mp3",
        destination=destination,
        work_dir=tmp_path,
    )

    assert destination.exists()


def test_manim_timeout_kills_descendants_and_keeps_the_original_traceback(tmp_path: Path) -> None:
    child_process_script = (
        "import subprocess, sys; "
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        "raise TypeError('wrong Manim call')"
    )

    with pytest.raises(ManimProcessTimeout, match="time limit") as error:
        _run_manim(
            [sys.executable, "-c", child_process_script],
            timeout=1,
            work_dir=tmp_path,
        )

    assert "TypeError: wrong Manim call" in error.value.stderr
