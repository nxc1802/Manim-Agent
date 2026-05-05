from __future__ import annotations

import pytest
from ai_engine.rag.reviewer_context import build_reviewer_rag_context, _format_api_reference
from unittest.mock import MagicMock, patch

def test_build_reviewer_rag_context_empty():
    assert build_reviewer_rag_context("") is None

@patch("ai_engine.rag.reviewer_context.parse_render_error")
def test_build_reviewer_rag_context_parse_fail(mock_parse):
    mock_parse.side_effect = ValueError("boom")
    assert build_reviewer_rag_context("logs") is None

@patch("ai_engine.rag.reviewer_context.ManimAPIRegistry")
def test_build_reviewer_rag_context_no_entries(mock_reg_cls):
    mock_reg = mock_reg_cls.return_value
    mock_reg.resolve_error.return_value = []
    mock_reg.find_similar.return_value = []
    assert build_reviewer_rag_context("NameError: x") is None

@patch("ai_engine.rag.reviewer_context.ManimAPIRegistry")
def test_build_reviewer_rag_context_success(mock_reg_cls):
    mock_reg = mock_reg_cls.return_value
    mock_reg.resolve_error.return_value = [{"symbol": "X", "description": "desc"}]
    mock_reg.lookup_deprecated.return_value = None
    
    ctx = build_reviewer_rag_context("NameError: name 'X' is not defined")
    assert ctx is not None
    assert "### 📚 MANIM_API_REFERENCE" in ctx
    assert "#### `X`" in ctx

def test_format_api_reference_deprecated():
    from ai_engine.rag.log_parser import ParsedError
    err = ParsedError("NameError", "ShowCreation", None, "", 10, "msg")
    entries = [{"symbol": "Create", "description": "desc"}]
    
    with patch("ai_engine.rag.reviewer_context.ManimAPIRegistry") as mock_reg_cls:
        mock_reg = mock_reg_cls.return_value
        mock_reg.lookup_deprecated.return_value = ("Create", entries[0])
        
        res = _format_api_reference(err, entries)
        assert "[!IMPORTANT]" in res
        assert "DEPRECATED" in res

def test_format_api_reference_common_errors():
    from ai_engine.rag.log_parser import ParsedError
    err = ParsedError("NameError", "ShowCreation", None, "", 10, "msg")
    entries = [{
        "symbol": "Create", 
        "common_errors": [{"pattern": "ShowCreation", "fix": "Use Create"}]
    }]
    
    with patch("ai_engine.rag.reviewer_context.ManimAPIRegistry") as mock_reg_cls:
        res = _format_api_reference(err, entries)
        assert "**Pro Tip**: Use Create" in res
