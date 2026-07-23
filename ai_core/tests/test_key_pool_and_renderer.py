from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from app.config import Settings
from app.llm import GoogleAPIKeyPool, GoogleLLM, KeyState
from app.renderer import (
    ManimProcessTimeout,
    UnsafeManimCode,
    _is_transient_frame_allocation_failure,
    _is_transient_partial_movie_list_failure,
    _mux_audio,
    _recover_partial_movie_concat,
    _run_manim,
    _sanitized_subprocess_env,
    render_manim_for_validation,
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


def test_google_key_pool_round_robins_in_ring_order() -> None:
    pool = GoogleAPIKeyPool(["key-a", "key-b", "key-c"])

    selected = [pool.acquire()[0] for _ in range(5)]

    assert selected == ["key-a", "key-b", "key-c", "key-a", "key-b"]


def test_google_key_pool_allocates_distinct_ring_positions_concurrently() -> None:
    pool = GoogleAPIKeyPool(["key-a", "key-b", "key-c"])

    with ThreadPoolExecutor(max_workers=3) as executor:
        selected = list(executor.map(lambda _: pool.acquire()[0], range(3)))

    assert set(selected) == {"key-a", "key-b", "key-c"}


def test_non_quota_provider_error_also_temporarily_cools_the_key() -> None:
    pool = GoogleAPIKeyPool(["key-a"])
    _, identity = pool.acquire()

    pool.record_failure(identity, RuntimeError("upstream connection reset"))

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


def test_stream_does_not_replay_prompt_after_emitting_a_token(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import app.llm as llm_module

    class BrokenStream:
        def __aiter__(self):  # noqa: ANN201
            return self

        async def __anext__(self):  # noqa: ANN201
            if not hasattr(self, "sent"):
                self.sent = True
                return SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="first"))]
                )
            raise RuntimeError("connection reset")

    calls = 0

    async def fake_completion(**_kwargs):  # noqa: ANN202
        nonlocal calls
        calls += 1
        return BrokenStream()

    monkeypatch.setattr(llm_module, "acompletion", fake_completion)
    client = GoogleLLM(GoogleAPIKeyPool(["key-a", "key-b"]))

    async def consume() -> list[str]:
        chunks: list[str] = []
        with pytest.raises(RuntimeError, match="interrupted after output began"):
            async for chunk in client.stream(
                messages=[{"role": "user", "content": "test"}],
                model="gemini-3.5-flash",
                temperature=0.1,
                max_tokens=32,
            ):
                chunks.append(chunk)
        return chunks

    assert asyncio.run(consume()) == ["first"]
    assert calls == 1


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


def test_validation_retries_only_manim_partial_movie_list_race(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    import app.renderer as renderer

    first_workspace = tmp_path / "first"
    second_workspace = tmp_path / "second"
    first_workspace.mkdir()
    second_workspace.mkdir()
    directories = iter((str(first_workspace), str(second_workspace)))
    monkeypatch.setattr(renderer.tempfile, "mkdtemp", lambda **_kwargs: next(directories))
    transient_error = (
        "FileNotFoundError: /tmp/media/videos/scene/480p15/"
        "partial_movie_files/GeneratedScene/partial_movie_file_list.txt"
    )
    run_manim = Mock(
        side_effect=[
            subprocess.CompletedProcess([], 1, "", transient_error),
            subprocess.CompletedProcess([], 0, "", ""),
        ]
    )
    monkeypatch.setattr(
        renderer,
        "_run_manim",
        run_manim,
    )
    result = render_manim_for_validation(
        "from manim import *\nclass GeneratedScene(Scene):\n    def construct(self): pass\n"
    )

    assert result.success is True
    assert result.temp_dir == str(second_workspace)
    assert not first_workspace.exists()
    assert "--disable_caching" in run_manim.call_args_list[1].args[0]
    assert _is_transient_partial_movie_list_failure(transient_error)
    assert not _is_transient_partial_movie_list_failure("FileNotFoundError: assets/chart.csv")


def test_partial_movie_concat_is_recovered_with_ffmpeg(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    media_dir = tmp_path / "media"
    partial_dir = (
        media_dir
        / "videos"
        / "scene"
        / "480p15"
        / "partial_movie_files"
        / "GeneratedScene"
    )
    partial_dir.mkdir(parents=True)
    first = partial_dir / "first.mp4"
    second = partial_dir / "second.mp4"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    list_file = partial_dir / "partial_movie_file_list.txt"
    list_file.write_text(
        f"file 'file:{first}'\nfile 'file:{second}'\n",
        encoding="utf-8",
    )

    def fake_ffmpeg(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        Path(command[-1]).write_bytes(b"recovered-video")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_ffmpeg)

    recovered = _recover_partial_movie_concat(media_dir, work_dir=tmp_path)

    expected = partial_dir.parent.parent / "GeneratedScene.mp4"
    assert recovered == expected
    assert expected.read_bytes() == b"recovered-video"


def test_validation_does_not_spend_llm_attempt_on_persistent_concat_failure(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    import app.renderer as renderer

    first_workspace = tmp_path / "first"
    second_workspace = tmp_path / "second"
    first_workspace.mkdir()
    second_workspace.mkdir()
    directories = iter((str(first_workspace), str(second_workspace)))
    monkeypatch.setattr(renderer.tempfile, "mkdtemp", lambda **_kwargs: next(directories))
    transient_error = (
        "FileNotFoundError: /tmp/media/videos/scene/480p15/"
        "partial_movie_files/GeneratedScene/partial_movie_file_list.txt"
    )
    monkeypatch.setattr(
        renderer,
        "_run_manim",
        Mock(return_value=subprocess.CompletedProcess([], 1, "", transient_error)),
    )

    result = render_manim_for_validation(
        "from manim import *\nclass GeneratedScene(Scene):\n    def construct(self): pass\n"
    )

    assert result.success is True
    assert result.video_path is None
    assert result.temp_dir == str(second_workspace)


def test_validation_retries_small_frame_allocation_failure(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    import app.renderer as renderer

    first_workspace = tmp_path / "first"
    second_workspace = tmp_path / "second"
    first_workspace.mkdir()
    second_workspace.mkdir()
    directories = iter((str(first_workspace), str(second_workspace)))
    monkeypatch.setattr(renderer.tempfile, "mkdtemp", lambda **_kwargs: next(directories))
    memory_error = (
        "MemoryError: Unable to allocate 1.56 MiB for an array "
        "with shape (480, 854, 4) and data type uint8"
    )
    run_manim = Mock(
        side_effect=[
            subprocess.CompletedProcess([], 1, "", memory_error),
            subprocess.CompletedProcess([], 0, "", ""),
        ]
    )
    monkeypatch.setattr(renderer, "_run_manim", run_manim)

    result = render_manim_for_validation(
        "from manim import *\nclass GeneratedScene(Scene):\n    def construct(self): pass\n"
    )

    assert result.success is True
    assert result.temp_dir == str(second_workspace)
    assert not first_workspace.exists()
    assert "--disable_caching" in run_manim.call_args_list[1].args[0]
    assert _is_transient_frame_allocation_failure(memory_error)
    assert not _is_transient_frame_allocation_failure(
        "MemoryError: Unable to allocate 2.00 GiB for an array with shape (10000, 10000)"
    )


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


def test_tts_gemini_primary_honors_voice_and_directing_controls(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    from unittest.mock import MagicMock

    import app.tts as tts

    monkeypatch.setattr(tts, "configured_google_keys", lambda: ["test-key"])
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "candidates": [{"content": {"parts": [{"inlineData": {"data": "AAE="}}]}}]
    }
    request = MagicMock(return_value=response)
    monkeypatch.setattr(tts.httpx, "post", request)

    def fake_ffmpeg(command, **_kwargs):  # type: ignore[no-untyped-def]
        Path(command[-1]).write_bytes(b"mp3")
        return __import__("subprocess").CompletedProcess(command, 0)

    monkeypatch.setattr(tts.subprocess, "run", fake_ffmpeg)
    destination = tmp_path / "voice.mp3"
    audio = synthesize_speech(
        narration="Xin chào",
        source_language="vi",
        user_settings={
            "tts_enabled": True,
            "tts_voice": "vi-VN-male",
            "tts_speaking_rate": 1.25,
            "tts_pitch": 2,
        },
        destination=destination,
    )

    assert audio == destination
    assert request.call_count == 1
    payload = request.call_args.kwargs["json"]
    assert payload["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Charon"
    prompt = payload["contents"][0]["parts"][0]["text"]
    assert "fast pace" in prompt
    assert "higher-pitched" in prompt


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
