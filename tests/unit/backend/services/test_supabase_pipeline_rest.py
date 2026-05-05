from __future__ import annotations
from typing import Any, Generator

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from backend.services.supabase_pipeline_rest import insert_agent_log_row, insert_pipeline_run_row
from shared.schemas.review_pipeline import AgentLog


@pytest.fixture
def supabase_config() -> Generator[Any, None, None]:
    with patch("backend.services.supabase_pipeline_rest.settings") as mock_settings:
        mock_settings.supabase_url = "https://example.supabase.co"
        mock_settings.supabase_service_role_key = "service-role-key"
        yield mock_settings


def test_insert_pipeline_run_row_success(supabase_config: Any) -> None:
    rid = uuid4()
    pid = uuid4()
    sid = uuid4()

    with patch("httpx.Client") as mock_client:
        mock_instance = mock_client.return_value.__enter__.return_value
        mock_instance.post.return_value = MagicMock(status_code=201)

        insert_pipeline_run_row(
            run_id=rid,
            project_id=pid,
            scene_id=sid,
            status="running",
            report={"usage_summary": {"total_prompt_tokens": 100}},
        )
        assert mock_instance.post.called


def test_insert_pipeline_run_row_fail(supabase_config: Any) -> None:
    rid = uuid4()
    pid = uuid4()
    sid = uuid4()

    with patch("httpx.Client") as mock_client:
        mock_instance = mock_client.return_value.__enter__.return_value
        mock_instance.post.side_effect = Exception("network error")

        # Should not raise because of try-except block in the function
        insert_pipeline_run_row(
            run_id=rid, project_id=pid, scene_id=sid, status="running", report={}
        )


def test_insert_agent_log_row_success(supabase_config: Any) -> None:
    log = AgentLog(
        run_id=uuid4(),
        scene_id=uuid4(),
        round_idx=1,
        agent_name="builder",
        system_prompt="sys",
        user_prompt="usr",
        output_text="code",
        metrics={"duration_ms": 100},
    )

    with patch("httpx.Client") as mock_client:
        mock_instance = mock_client.return_value.__enter__.return_value
        mock_instance.post.return_value = MagicMock(status_code=201)

        insert_agent_log_row(log)
        assert mock_instance.post.called


def test_insert_agent_log_row_not_configured() -> None:
    with patch("backend.services.supabase_pipeline_rest.settings") as mock_settings:
        mock_settings.supabase_url = None

        log = MagicMock()
        insert_agent_log_row(log)
        # Should return early
