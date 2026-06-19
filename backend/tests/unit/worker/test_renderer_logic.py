from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from worker.renderer import manim_quality_flags, render_manim_scene_to_disk


@pytest.fixture(autouse=True)
def mock_disk_space() -> Generator[None, None, None]:
    with patch("worker.renderer.shutil.disk_usage", return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3)):
        yield


@pytest.fixture()
def mock_job_store() -> Generator[Any, None, None]:
    with patch("worker.renderer.RedisRenderJobStore") as mock:
        yield mock.return_value


@pytest.fixture()
def mock_content_store() -> Generator[Any, None, None]:
    with patch("worker.renderer.get_content_store") as mock:
        yield mock.return_value


@patch("worker.renderer.subprocess.Popen")
@patch("worker.renderer.Path.rglob")
def test_render_manim_scene_to_disk_injects_metadata(
    mock_rglob: MagicMock,
    mock_popen: MagicMock,
    mock_content_store: MagicMock,
    mock_job_store: MagicMock,
    tmp_path: Path,
) -> None:
    # Setup job
    job_id = uuid4()
    scene_id = uuid4()
    mock_job_store.get.return_value = MagicMock(scene_id=scene_id)

    # Setup scene
    mcode = """from manim import *
class GeneratedScene(Scene):
    def construct(self):
        pass
"""
    sync_segments = {"intro": 1.5, "step1": 2.0}
    mock_content_store.get_scene.return_value = MagicMock(
        manim_code=mcode, sync_segments=sync_segments, manim_code_version=1
    )

    # Mock subprocess and rglob
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ("stdout", "stderr")
    mock_proc.returncode = 0
    mock_popen.return_value = mock_proc
    video_mock = MagicMock()
    video_mock.is_file.return_value = True
    mock_rglob.return_value = [video_mock]

    # Run
    with patch("worker.renderer.tempfile.mkdtemp", return_value=str(tmp_path)):
        render_manim_scene_to_disk(job_id=job_id, job_type="preview", quality="720p")

    # Verify file content
    generated_py = tmp_path / "generated_scene.py"
    assert generated_py.exists()
    content = generated_py.read_text()

    assert "BEAT_DURATIONS = " in content
    assert json.dumps(sync_segments) in content
    assert "class GeneratedScene(Scene):" in content

    # Verify future imports stay at top if present
    mcode_with_future = "from __future__ import annotations\n" + mcode
    mock_content_store.get_scene.return_value.manim_code = mcode_with_future

    with patch("worker.renderer.tempfile.mkdtemp", return_value=str(tmp_path / "v2")):
        (tmp_path / "v2").mkdir()
        render_manim_scene_to_disk(job_id=job_id, job_type="preview", quality="720p")

    scene_file = tmp_path / "v2" / "generated_scene.py"
    saved_code = scene_file.read_text()
    assert "BEAT_DURATIONS = " in saved_code
    assert '"intro": 1.5' in saved_code


@patch("worker.renderer.subprocess.Popen")
def test_render_manim_scene_to_disk_handles_failure(
    mock_popen: MagicMock,
    mock_content_store: MagicMock,
    mock_job_store: MagicMock,
    tmp_path: Path,
) -> None:

    job_id = uuid4()
    mock_job_store.get.return_value = MagicMock(scene_id=uuid4())
    mock_content_store.get_scene.return_value = MagicMock(manim_code="x=1", sync_segments={})

    # Mock failure
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ("stdout", "Manim Error")
    mock_proc.returncode = 1
    mock_popen.return_value = mock_proc

    with pytest.raises(RuntimeError, match="Manim Error"):
        render_manim_scene_to_disk(job_id=job_id, job_type="preview", quality="720p")


def test_manim_quality_flags() -> None:
    assert manim_quality_flags(job_type="preview", quality="720p") == ["-qh"]
    assert manim_quality_flags(job_type="full", quality="4k") == ["-qk"]
    assert manim_quality_flags(job_type="full", quality="1080p") == ["-qh"]
    assert manim_quality_flags(job_type="full", quality="720p") == ["-qh"]


def test_render_manim_scene_to_disk_errors(mock_job_store: Any, mock_content_store: Any) -> None:
    job_id = uuid4()

    # Job not found
    mock_job_store.get.return_value = None
    with pytest.raises(RuntimeError, match="Render job not found"):
        render_manim_scene_to_disk(job_id=job_id, job_type="preview", quality="720p")

    # Scene not found
    mock_job_store.get.return_value = MagicMock(scene_id=uuid4())
    mock_content_store.get_scene.return_value = None
    with pytest.raises(RuntimeError, match="not found in content store"):
        render_manim_scene_to_disk(job_id=job_id, job_type="preview", quality="720p")

    # Missing code
    mock_content_store.get_scene.return_value = MagicMock(manim_code="")
    with pytest.raises(RuntimeError, match="missing manim_code"):
        render_manim_scene_to_disk(job_id=job_id, job_type="preview", quality="720p")


@patch("worker.renderer.subprocess.Popen")
@patch("worker.renderer.Path.rglob")
@patch("worker.renderer.IS_POSIX", True)
def test_render_manim_scene_to_disk_sets_resource_limits_on_posix(
    mock_rglob: MagicMock,
    mock_popen: MagicMock,
    mock_content_store: MagicMock,
    mock_job_store: MagicMock,
    tmp_path: Path,
) -> None:
    import os
    import sys
    
    # Mock resource module
    mock_resource = MagicMock()
    sys.modules["resource"] = mock_resource
    
    try:
        job_id = uuid4()
        mock_job_store.get.return_value = MagicMock(scene_id=uuid4())
        mock_content_store.get_scene.return_value = MagicMock(manim_code="class GeneratedScene: pass", sync_segments={}, audio_url=None)

        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("stdout", "stderr")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        video_mock = MagicMock()
        video_mock.is_file.return_value = True
        mock_rglob.return_value = [video_mock]

        with patch("worker.renderer.tempfile.mkdtemp", return_value=str(tmp_path)):
            with patch.dict(os.environ, {"RENDERER_MAX_VMEM_BYTES": "1000", "RENDERER_MAX_FSIZE_BYTES": "2000"}):
                render_manim_scene_to_disk(job_id=job_id, job_type="preview", quality="720p")

        # Verify that popen was called with preexec_fn
        assert "preexec_fn" in mock_popen.call_args[1]
        preexec_fn = mock_popen.call_args[1]["preexec_fn"]
        assert preexec_fn is not None

        # Execute preexec_fn to test its internal setrlimit logic
        with patch("worker.renderer.os.setsid", create=True) as mock_setsid:
            preexec_fn()
            mock_setsid.assert_called_once()
            
        mock_resource.setrlimit.assert_any_call(mock_resource.RLIMIT_CPU, (1210, 1215))
        mock_resource.setrlimit.assert_any_call(mock_resource.RLIMIT_AS, (1000, 1000))
        mock_resource.setrlimit.assert_any_call(mock_resource.RLIMIT_FSIZE, (2000, 2000))
    finally:
        sys.modules.pop("resource", None)
