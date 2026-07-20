from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess
from uuid import uuid4

import pytest
from app import main
from app.config import settings
from app.renderer import _materialize_concat_source, concat_project_videos, render_full_project


class _ReadyRedis:
    @classmethod
    def from_url(cls, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        return cls()

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        return None


def test_ai_core_readiness_reports_runtime_and_dependencies(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(main, "Redis", _ReadyRedis)
    monkeypatch.setattr(main, "configured_google_keys", lambda: ["configured"])

    response = main.ready()
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload["checks"]["redis"]["ok"] is True
    assert payload["checks"]["provider_keys"]["ok"] is True
    assert payload["checks"]["manim"]["version"]


def test_ai_core_readiness_fails_without_provider_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(main, "Redis", _ReadyRedis)
    monkeypatch.setattr(main, "configured_google_keys", list)

    response = main.ready()

    assert response.status_code == 503


def test_ai_core_public_http_surface_is_readiness_only() -> None:
    methods = {"get", "post", "patch", "put", "delete"}
    actual = {
        (method.upper(), path)
        for path, definition in main.app.openapi()["paths"].items()
        for method in definition
        if method in methods
    }

    assert actual == {("GET", "/health"), ("GET", "/ready")}


def test_concat_local_source_is_confined_to_artifact_root(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    scene = artifacts / "scene.mp4"
    scene.write_bytes(b"video")
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"video")
    monkeypatch.setattr(settings, "artifacts_dir", artifacts)

    assert _materialize_concat_source(scene.as_uri(), tmp_path, 0) == scene
    with pytest.raises(RuntimeError, match="not allowed"):
        _materialize_concat_source(outside.as_uri(), tmp_path, 1)


def test_concat_rejects_unsigned_storage_scheme(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Unsupported scene artifact scheme"):
        _materialize_concat_source("supabase://videos/project/scene.mp4", tmp_path, 0)


def test_full_project_tts_synthesizes_every_scene_before_concat(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    import app.renderer as renderer

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    monkeypatch.setattr(settings, "artifacts_dir", artifacts)
    source_one, source_two = tmp_path / "one.mp4", tmp_path / "two.mp4"
    source_one.write_bytes(b"video")
    source_two.write_bytes(b"video")
    sources = [source_one, source_two]
    muxed: list[Path] = []

    monkeypatch.setattr(
        renderer,
        "_materialize_concat_source",
        lambda _url, _temp, index: sources[index],
    )

    def fake_synthesize(*, destination: Path, **_kwargs):  # type: ignore[no-untyped-def]
        destination.write_bytes(b"audio")
        return destination

    def fake_mux(*, destination: Path, **_kwargs):  # type: ignore[no-untyped-def]
        destination.write_bytes(b"muxed")
        muxed.append(destination)

    def fake_ffmpeg(command, **_kwargs):  # type: ignore[no-untyped-def]
        Path(command[-1]).write_bytes(b"project")
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(renderer, "synthesize_speech", fake_synthesize)
    monkeypatch.setattr(renderer, "_mux_audio", fake_mux)
    monkeypatch.setattr(renderer, "_has_audio_stream", lambda *_args: True)
    monkeypatch.setattr(renderer.subprocess, "run", fake_ffmpeg)

    output = concat_project_videos(
        uuid4(),
        ["file:///one.mp4", "file:///two.mp4"],
        {"tts_enabled": True},
        ["First narration", "Second narration"],
        "en",
    )

    assert len(muxed) == 2
    assert output == (artifacts / f"{output.rsplit('/', 1)[-1]}").as_uri()


def test_final_project_rerenders_sources_and_skips_invalid_scenes(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    import app.renderer as renderer

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    monkeypatch.setattr(settings, "artifacts_dir", artifacts)
    rendered_codes: list[str] = []

    def fake_render(intermediate_id, code, *_args):  # type: ignore[no-untyped-def]
        if code == "BROKEN":
            raise renderer.UnsafeManimCode("GeneratedScene is invalid")
        rendered_codes.append(code)
        path = artifacts / f"{intermediate_id}.mp4"
        path.write_bytes(b"scene")
        return path.as_uri()

    concat_inputs: list[str] = []

    def fake_concat(job_id, urls, concat_settings, *_args):  # type: ignore[no-untyped-def]
        concat_inputs.extend(urls)
        assert concat_settings["tts_enabled"] is False
        output = artifacts / f"{job_id}.mp4"
        output.write_bytes(b"project-with-audio")
        return output.as_uri()

    monkeypatch.setattr(renderer, "render_manim_code", fake_render)
    monkeypatch.setattr(renderer, "concat_project_videos", fake_concat)
    monkeypatch.setattr(renderer, "_has_audio_stream", lambda *_args: True)

    result = render_full_project(
        uuid4(),
        [
            {"scene_id": "1", "scene_order": 1, "manim_code": "VALID_1", "voice_script": "One"},
            {"scene_id": "2", "scene_order": 2, "manim_code": "BROKEN", "voice_script": "Two"},
            {"scene_id": "3", "scene_order": 3, "manim_code": "VALID_3", "voice_script": "Three"},
        ],
        {"tts_enabled": True},
        "en",
    )

    assert rendered_codes == ["VALID_1", "VALID_3"]
    assert len(concat_inputs) == 2
    assert "Skipped Scene 2" in result.logs
    assert "Rendered Scene 1 from source" in result.logs
