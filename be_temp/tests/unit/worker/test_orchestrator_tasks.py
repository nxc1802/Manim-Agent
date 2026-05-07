from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from worker.orchestrator_tasks import run_orchestrator_loop_task


def test_run_orchestrator_loop_task_success() -> None:
    sid = str(uuid4())
    mock_self = MagicMock()
    mock_self.request.headers = {"trace_id": "t1"}

    with patch("ai_engine.orchestrator.run_builder_loop_phase") as mock_run:
        mock_run.return_value = (MagicMock(), {"status": "ok"})

        # We need to mock all the internal imports in the function
        with (
            patch("worker.orchestrator_tasks.UUID") as mock_uuid,
            patch("backend.db.content_store.get_content_store"),
            patch("backend.services.redis_client.get_redis"),
            patch("backend.api.deps.get_llm_client"),
            patch("backend.api.deps.get_runtime_limits") as mock_rt,
        ):
            mock_uuid.return_value = uuid4()
            mock_rt.return_value.preview_poll_timeout_seconds = 10

            res = run_orchestrator_loop_task.__wrapped__(sid)
            assert res == {"status": "ok"}
            assert mock_run.called


def test_run_orchestrator_loop_task_error() -> None:
    sid = str(uuid4())
    mock_self = MagicMock()
    mock_self.request.headers = {}

    with patch("ai_engine.orchestrator.run_builder_loop_phase") as mock_run:
        mock_run.side_effect = Exception("boom")

        with (
            patch("backend.db.content_store.get_content_store"),
            patch("backend.services.redis_client.get_redis"),
            patch("backend.api.deps.get_llm_client"),
            patch("backend.api.deps.get_runtime_limits"),
        ):
            with pytest.raises(Exception, match="boom"):
                run_orchestrator_loop_task.__wrapped__(sid)
