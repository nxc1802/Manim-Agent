from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.config import settings
from app.errors import InactiveStepError
from app.worker import _remove_uploaded_local_artifact, generate_hitl_step


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


def test_inactive_step_stops_without_failure_callback() -> None:
    step_id = uuid4()
    client = MagicMock()
    client.__enter__.return_value = client
    client.claim_step.return_value = {"step": {"id": step_id, "kind": "builder"}}
    executor = MagicMock()
    executor.generate.side_effect = InactiveStepError("inactive")

    with (
        patch("app.worker.BackendClient", return_value=client),
        patch("app.worker.StepExecutor", return_value=executor),
        patch("app.worker._StepHeartbeat") as heartbeat_type,
    ):
        heartbeat_type.return_value.__enter__.return_value = heartbeat_type.return_value
        generate_hitl_step.run(str(step_id))

    client.complete_step.assert_not_called()
    client.fail_step.assert_not_called()


def test_heartbeat_stops_before_step_completion_callback() -> None:
    step_id = uuid4()
    events: list[str] = []
    client = MagicMock()
    client.__enter__.return_value = client
    client.claim_step.return_value = {"step": {"id": step_id, "kind": "builder"}}
    client.complete_step.side_effect = lambda *_args: events.append("completed")
    executor = MagicMock()
    executor.generate.return_value = {"manim_code": "valid"}
    heartbeat = MagicMock()
    heartbeat.__enter__.return_value = heartbeat
    heartbeat.__exit__.side_effect = lambda *_args: events.append("heartbeat_stopped")

    with (
        patch("app.worker.BackendClient", return_value=client),
        patch("app.worker.StepExecutor", return_value=executor),
        patch("app.worker._StepHeartbeat", return_value=heartbeat),
    ):
        generate_hitl_step.run(str(step_id))

    assert events == ["heartbeat_stopped", "completed"]
    heartbeat.raise_if_inactive.assert_called_with()
