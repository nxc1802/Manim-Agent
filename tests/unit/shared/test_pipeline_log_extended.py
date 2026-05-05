from __future__ import annotations

import os
import pytest
import logging
from shared.pipeline_log import (
    setup_pipeline_logging,
    _get_broadcast_redis,
    _pipeline_log_level,
    pipeline_event,
    pipeline_debug,
    pipeline_error,
    trace_id_from_celery_request,
    celery_trace_headers,
    LOG
)
from unittest.mock import MagicMock, patch

def test_pipeline_log_level_fallback():
    with patch.dict(os.environ, {"LOG_LEVEL": "", "PIPELINE_LOG_LEVEL": "DEBUG"}):
        assert _pipeline_log_level() == logging.DEBUG

def test_get_broadcast_redis_fail():
    with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"}):
        with patch("redis.from_url") as mock_from:
            mock_from.side_effect = Exception("conn failed")
            # Clear cache
            with patch("shared.pipeline_log._BROADCAST_REDIS", None):
                assert _get_broadcast_redis() is None

def test_trace_id_from_celery_request_none():
    assert trace_id_from_celery_request(None) is None
    
    mock_req = MagicMock()
    mock_req.headers = None
    assert trace_id_from_celery_request(mock_req) is None

def test_celery_trace_headers_empty():
    assert celery_trace_headers(None) == {}
    assert celery_trace_headers(" ") == {}

@patch("shared.pipeline_log._get_broadcast_redis")
def test_pipeline_event_with_redis(mock_get_redis):
    mock_r = MagicMock()
    mock_get_redis.return_value = mock_r
    
    # Force DEBUG level to trigger _emit_human_readable
    with patch.object(LOG, "level", logging.DEBUG):
        pipeline_event("comp", "phase", "msg", details={"a": "b" * 1001})
        assert mock_r.publish.called

@patch("shared.pipeline_log._get_broadcast_redis")
def test_pipeline_debug_with_redis(mock_get_redis):
    mock_r = MagicMock()
    mock_get_redis.return_value = mock_r
    
    pipeline_debug("comp", "phase", "msg")
    assert mock_r.publish.called

@patch("shared.pipeline_log._get_broadcast_redis")
def test_pipeline_error_with_redis(mock_get_redis):
    mock_r = MagicMock()
    mock_get_redis.return_value = mock_r
    
    pipeline_error("comp", "phase", "msg")
    assert mock_r.publish.called
