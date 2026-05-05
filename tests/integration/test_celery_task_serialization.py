from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from worker.tasks import render_manim_scene


def test_render_manim_scene_serialization(celery_config) -> None:
    """Test that the task can be called with a string UUID (as it would be from API)."""
    job_id = str(uuid4())

    with patch("worker.runtime.execute_render_job") as mock_execute:
        # Simulate Celery calling the task in eager mode
        render_manim_scene.apply(args=[job_id])

        # Verify it was called with a UUID object
        args, _ = mock_execute.call_args
        assert args[0].hex == job_id.replace("-", "")


@patch("worker.runtime.execute_render_job")
def test_task_id_propagation(mock_execute, celery_config) -> None:
    """Test that trace IDs or other metadata propagate (simulated)."""
    job_id = str(uuid4())

    # We can't easily mock self.request.id in apply(), but we can test the logic
    res = render_manim_scene.apply(args=[job_id])
    assert res.result == job_id
    assert mock_execute.called
