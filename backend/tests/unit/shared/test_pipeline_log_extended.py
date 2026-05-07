from __future__ import annotations

import logging
import os
from unittest.mock import MagicMock, patch

from shared.pipeline_log import (
    LOG,
    _pipeline_log_level,
    celery_trace_headers,
    pipeline_debug,
    pipeline_error,
    pipeline_event,
    trace_id_from_celery_request,
)


def test_pipeline_log_level_fallback() -> None:
    with patch.dict(os.environ, {"LOG_LEVEL": "", "PIPELINE_LOG_LEVEL": "DEBUG"}):
        assert _pipeline_log_level() == logging.DEBUG


def test_trace_id_from_celery_request_none() -> None:
    assert trace_id_from_celery_request(None) is None

    mock_req = MagicMock()
    mock_req.headers = None
    assert trace_id_from_celery_request(mock_req) is None


def test_celery_trace_headers_empty() -> None:
    assert celery_trace_headers(None) == {}
    assert celery_trace_headers(" ") == {}


@patch("httpx.Client")
def test_pipeline_event_with_supabase(mock_httpx: MagicMock) -> None:
    mock_client = MagicMock()
    mock_httpx.return_value.__enter__.return_value = mock_client

    with patch.dict(os.environ, {"SUPABASE_URL": "http://mock", "SUPABASE_SERVICE_ROLE_KEY": "key"}):
        from shared.pipeline_log import setup_pipeline_logging
        setup_pipeline_logging(supabase_url="http://mock", supabase_key="key")
        
        # Force DEBUG level to trigger _emit_human_readable
        with patch.object(LOG, "level", logging.DEBUG):
            pipeline_event("comp", "phase", "msg", project_id="123")
            assert mock_client.post.called


@patch("httpx.Client")
def test_pipeline_error_with_supabase(mock_httpx: MagicMock) -> None:
    mock_client = MagicMock()
    mock_httpx.return_value.__enter__.return_value = mock_client

    with patch.dict(os.environ, {"SUPABASE_URL": "http://mock", "SUPABASE_SERVICE_ROLE_KEY": "key"}):
        from shared.pipeline_log import setup_pipeline_logging
        setup_pipeline_logging(supabase_url="http://mock", supabase_key="key")
        
        pipeline_error("comp", "phase", "msg", project_id="123")
        assert mock_client.post.called
