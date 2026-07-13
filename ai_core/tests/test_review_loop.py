from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.review_loop import (
    CODE_REVIEW_CONFIG,
    VISUAL_REVIEW_CONFIG,
    CodeFix,
    ReviewLoop,
    apply_partial_fix,
    is_same_error,
)
from app.renderer import ManimError, ManimRenderResult


# ---------------------------------------------------------------------------
# Unit: apply_partial_fix
# ---------------------------------------------------------------------------

def test_apply_partial_fix_replaces_first_occurrence() -> None:
    code = "a = 1\nb = 2\na = 1\n"
    result = apply_partial_fix(code, "a = 1", "a = 42")
    assert result == "a = 42\nb = 2\na = 1\n"


def test_apply_partial_fix_no_match_returns_unchanged() -> None:
    code = "x = 1\n"
    assert apply_partial_fix(code, "y = 2", "y = 3") == code


def test_apply_partial_fix_empty_original_returns_unchanged() -> None:
    code = "x = 1\n"
    assert apply_partial_fix(code, "", "y = 3") == code


# ---------------------------------------------------------------------------
# Unit: is_same_error
# ---------------------------------------------------------------------------

def test_same_error_true() -> None:
    a = ManimError(line=10, message="NameError: name 'foo' is not defined")
    b = ManimError(line=10, message="NameError: name 'foo' is not defined")
    assert is_same_error(a, b) is True


def test_same_error_different_line() -> None:
    a = ManimError(line=10, message="NameError")
    b = ManimError(line=20, message="NameError")
    assert is_same_error(a, b) is False


def test_same_error_different_message() -> None:
    a = ManimError(line=10, message="NameError")
    b = ManimError(line=10, message="TypeError")
    assert is_same_error(a, b) is False


def test_same_error_none_lines_match_on_message() -> None:
    a = ManimError(line=None, message="generic error")
    b = ManimError(line=None, message="generic error")
    assert is_same_error(a, b) is True


def test_same_error_with_dicts() -> None:
    a = {"line": 5, "message": "err"}
    b = {"line": 5, "message": "err"}
    assert is_same_error(a, b) is True


# ---------------------------------------------------------------------------
# Unit: ReviewLoop with mocks
# ---------------------------------------------------------------------------

def _make_loop(llm_mock=None) -> ReviewLoop:
    """Build a ReviewLoop with a mock LLM and single-model tiers for fast testing."""
    from app.models import ModelTier
    tiers = [ModelTier(model="test-model", max_attempts=2)]
    return ReviewLoop(llm=llm_mock or MagicMock(), tiers=tiers)


def test_review_loop_passes_on_valid_code() -> None:
    """If manim render succeeds, the loop should pass immediately."""
    mock_render = ManimRenderResult(success=True, stderr="", stdout="", temp_dir=None)
    with patch("app.review_loop.render_manim_for_validation", return_value=mock_render):
        loop = _make_loop()
        result = loop.run("valid code", CODE_REVIEW_CONFIG)
    assert result.passed is True
    assert result.total_attempts == 1
    assert len(result.iterations) == 0


def test_review_loop_fixes_error_on_first_try() -> None:
    """If the LLM fix resolves the error, the loop should pass."""
    # First call: error. Second call (after fix): success.
    fail_render = ManimRenderResult(
        success=False, stderr='File "scene.py", line 5\nNameError: bad', stdout="", temp_dir=None,
    )
    pass_render = ManimRenderResult(success=True, stderr="", stdout="", temp_dir=None)

    llm = MagicMock()
    llm.complete.return_value = '{"can_fix": true, "original_code": "bad_line", "replacement_code": "good_line", "explanation": "fixed"}'

    with patch("app.review_loop.render_manim_for_validation", side_effect=[fail_render, pass_render]):
        loop = _make_loop(llm)
        result = loop.run("code with bad_line", CODE_REVIEW_CONFIG)

    assert result.passed is True
    assert result.total_attempts == 1
    assert "bad_line" not in result.manim_code
    assert "good_line" in result.manim_code


def test_review_loop_escalates_on_same_error() -> None:
    """If the same error persists after a fix, the loop should escalate."""
    from app.models import ModelTier
    tiers = [
        ModelTier(model="weak", max_attempts=1),
        ModelTier(model="strong", max_attempts=1),
    ]
    fail_render = ManimRenderResult(
        success=False, stderr='File "scene.py", line 10\nNameError: oops', stdout="", temp_dir=None,
    )

    llm = MagicMock()
    llm.complete.return_value = '{"can_fix": true, "original_code": "x", "replacement_code": "y", "explanation": "try"}'

    with patch("app.review_loop.render_manim_for_validation", return_value=fail_render):
        loop = ReviewLoop(llm=llm, tiers=tiers)
        result = loop.run("code with x", CODE_REVIEW_CONFIG)

    assert result.passed is False
    assert len(result.iterations) >= 2
    # Both models should have attempted
    models_tried = {r.model for r in result.iterations}
    assert "weak" in models_tried
    assert "strong" in models_tried


def test_review_loop_escalates_when_model_cannot_fix() -> None:
    """If the LLM returns can_fix=false, escalate to next tier."""
    from app.models import ModelTier
    tiers = [
        ModelTier(model="m1", max_attempts=1),
        ModelTier(model="m2", max_attempts=1),
    ]
    fail_render = ManimRenderResult(
        success=False, stderr='File "scene.py", line 1\nSyntaxError: bad', stdout="", temp_dir=None,
    )

    llm = MagicMock()
    llm.complete.return_value = '{"can_fix": false, "original_code": "", "replacement_code": "", "explanation": "too complex"}'

    with patch("app.review_loop.render_manim_for_validation", return_value=fail_render):
        loop = ReviewLoop(llm=llm, tiers=tiers)
        result = loop.run("broken code", CODE_REVIEW_CONFIG)

    assert result.passed is False
    assert all(r.escalated for r in result.iterations)


def test_code_and_visual_review_configs_differ_only_in_prompts() -> None:
    """Both configs should use the same ReviewConfig class, differ in fields only."""
    assert type(CODE_REVIEW_CONFIG) is type(VISUAL_REVIEW_CONFIG)
    assert CODE_REVIEW_CONFIG.uses_vision is False
    assert VISUAL_REVIEW_CONFIG.uses_vision is True
    assert CODE_REVIEW_CONFIG.render_flags == []
    assert VISUAL_REVIEW_CONFIG.render_flags == ["-s"]
    # Both have prompts
    assert CODE_REVIEW_CONFIG.review_prompt != VISUAL_REVIEW_CONFIG.review_prompt
    assert CODE_REVIEW_CONFIG.fix_prompt != VISUAL_REVIEW_CONFIG.fix_prompt


def test_review_loop_catches_unsafe_code_exception() -> None:
    """If validate_manim_code raises UnsafeManimCode, the loop catches it and tries to fix."""
    from app.renderer import UnsafeManimCode
    llm = MagicMock()
    llm.complete.return_value = '{"can_fix": true, "original_code": "import os", "replacement_code": "", "explanation": "removed import"}'

    # First call throws UnsafeManimCode, second succeeds (success=True)
    mock_success = ManimRenderResult(success=True, stderr="", stdout="")

    with patch("app.review_loop.render_manim_for_validation") as mock_validate:
        mock_validate.side_effect = [UnsafeManimCode("Import is not allowed: os"), mock_success]
        loop = _make_loop(llm)
        result = loop.run("import os\nfrom manim import *", CODE_REVIEW_CONFIG)

    assert result.passed is True
    assert result.total_attempts == 1
    assert "import os" not in result.manim_code

