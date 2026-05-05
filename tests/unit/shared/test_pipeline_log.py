from __future__ import annotations

from unittest.mock import patch

from shared.pipeline_log import (
    get_pipeline_trace_id,
    pipeline_debug,
    pipeline_error,
    pipeline_event,
    pipeline_trace_id_var,
)


def test_pipeline_trace_id_context():
    pipeline_trace_id_var.set(None)
    assert get_pipeline_trace_id() is None
    pipeline_trace_id_var.set("test-trace")
    assert get_pipeline_trace_id() == "test-trace"
    pipeline_trace_id_var.set(None)
    assert get_pipeline_trace_id() is None


@patch("shared.pipeline_log.LOG")
def test_pipeline_log_methods(mock_log):
    import logging

    mock_log.level = logging.INFO
    pipeline_trace_id_var.set("trace-123")

    pipeline_debug("comp", "code", "msg", details={"x": 1})
    mock_log.debug.assert_called()

    pipeline_event("comp", "code", "msg")
    mock_log.info.assert_called()

    pipeline_error("comp", "code", "msg")
    mock_log.error.assert_called()

    pipeline_trace_id_var.set(None)


@patch("shared.pipeline_log.LOG")
def test_pipeline_log_no_trace(mock_log):
    import logging

    mock_log.level = logging.INFO
    pipeline_trace_id_var.set(None)
    pipeline_event("comp", "code", "msg")
    mock_log.info.assert_called()
