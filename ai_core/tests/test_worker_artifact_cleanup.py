from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.worker import _remove_uploaded_local_artifact


def test_uploaded_artifact_is_removed_after_durable_callback(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "artifacts_dir", tmp_path)
    artifact = tmp_path / "render.mp4"
    artifact.write_bytes(b"video")

    _remove_uploaded_local_artifact(
        f"file://{artifact}",
        {"asset_url": "supabase://videos/project/renders/render.mp4"},
    )

    assert not artifact.exists()


def test_local_only_artifact_is_retained(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "artifacts_dir", tmp_path)
    artifact = tmp_path / "render.mp4"
    artifact.write_bytes(b"video")
    local_url = f"file://{artifact}"

    _remove_uploaded_local_artifact(local_url, {"asset_url": local_url})

    assert artifact.exists()


def test_cleanup_refuses_paths_outside_artifact_root(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"video")
    monkeypatch.setattr(settings, "artifacts_dir", artifact_root)

    _remove_uploaded_local_artifact(
        f"file://{outside}",
        {"asset_url": "supabase://videos/project/renders/render.mp4"},
    )

    assert outside.exists()
