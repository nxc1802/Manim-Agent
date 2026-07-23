from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.renderer import ManimError, ManimRenderResult
from app.review_loop import (
    CODE_REVIEW_CONFIG,
    VISUAL_REVIEW_CONFIG,
    ReviewLoop,
    _parse_json,
    apply_partial_fix,
    is_same_error,
    semantic_strategy_fingerprint,
    validate_partial_fix,
)

# ---------------------------------------------------------------------------
# Unit: apply_partial_fix
# ---------------------------------------------------------------------------


def test_apply_partial_fix_replaces_a_unique_occurrence() -> None:
    code = "a = 1\nb = 2\nc = 3\n"
    result = apply_partial_fix(code, "a = 1", "a = 42")
    assert result == "a = 42\nb = 2\nc = 3\n"


def test_apply_partial_fix_no_match_returns_unchanged() -> None:
    code = "x = 1\n"
    assert apply_partial_fix(code, "y = 2", "y = 3") == code


def test_apply_partial_fix_empty_original_returns_unchanged() -> None:
    code = "x = 1\n"
    assert apply_partial_fix(code, "", "y = 3") == code


def test_partial_fix_rejects_full_file_rewrite() -> None:
    code = "line_one\nline_two\nline_three\n"
    reason = validate_partial_fix(code, code, "replacement\n")
    assert reason == "Reviewer attempted to replace the entire source file"
    assert apply_partial_fix(code, code, "replacement\n") == code


def test_partial_fix_rejects_ambiguous_or_oversized_replacement() -> None:
    duplicate = "value = 1\nvalue = 1\n"
    assert "exactly once" in (validate_partial_fix(duplicate, "value = 1", "value = 2") or "")

    code = "\n".join(f"line_{number}" for number in range(20))
    large_excerpt = "\n".join(f"line_{number}" for number in range(5))
    assert "limited to 4 lines" in (validate_partial_fix(code, large_excerpt, "fixed") or "")


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


@pytest.mark.parametrize(
    ("response", "expected_explanation"),
    [
        (
            'Result:\n```json\n{"can_fix": true, "original_code": "bad", '
            '"replacement_code": "good", "explanation": "fenced",}\n```',
            "fenced",
        ),
        (
            "{'can_fix': True, 'original_code': 'bad', "
            "'replacement_code': 'good', 'explanation': 'python literal'}",
            "python literal",
        ),
        (
            '{"can_fix": true, "original_code": "bad\nline", '
            '"replacement_code": "good", "explanation": "raw newline"}',
            "raw newline",
        ),
    ],
)
def test_parse_json_recovers_common_reviewer_wrappers(
    response: str, expected_explanation: str
) -> None:
    parsed = _parse_json(response)

    assert parsed["can_fix"] is True
    assert parsed["replacement_code"] == "good"
    assert parsed["explanation"] == expected_explanation


def test_parse_json_does_not_remove_comma_from_replacement_code() -> None:
    parsed = _parse_json(
        '{"can_fix": true, "original_code": "bad", '
        '"replacement_code": "print(\',}\')", "explanation": "safe",}'
    )

    assert parsed["replacement_code"] == "print(',}')"


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
    assert result.total_attempts == 0
    assert len(result.iterations) == 0


def test_review_loop_respects_user_attempt_limit() -> None:
    failed_render = ManimRenderResult(
        success=False,
        stderr='File "scene.py", line 5\nNameError: bad',
        stdout="",
        temp_dir=None,
    )
    llm = MagicMock()
    llm.complete.return_value = (
        '{"can_fix": false, "original_code": "", "replacement_code": "", '
        '"explanation": "Cannot fix"}'
    )

    with patch("app.review_loop.render_manim_for_validation", return_value=failed_render):
        result = _make_loop(llm).run("bad code", CODE_REVIEW_CONFIG, max_attempts=1)

    assert result.passed is False
    assert result.total_attempts == 1


def test_review_loop_fixes_error_on_first_try() -> None:
    """If the LLM fix resolves the error, the loop should pass."""
    # First call: error. Second call (after fix): success.
    fail_render = ManimRenderResult(
        success=False,
        stderr='File "scene.py", line 5\nNameError: bad',
        stdout="",
        temp_dir=None,
    )
    pass_render = ManimRenderResult(success=True, stderr="", stdout="", temp_dir=None)

    llm = MagicMock()
    llm.complete.return_value = '{"can_fix": true, "original_code": "bad_line", "replacement_code": "good_line", "explanation": "fixed"}'

    with patch(
        "app.review_loop.render_manim_for_validation", side_effect=[fail_render, pass_render]
    ):
        loop = _make_loop(llm)
        result = loop.run("code with bad_line", CODE_REVIEW_CONFIG)

    assert result.passed is True
    assert result.total_attempts == 1
    assert "bad_line" not in result.manim_code
    assert "good_line" in result.manim_code


def test_render_timeout_with_traceback_still_enters_the_repair_path() -> None:
    timeout_render = ManimRenderResult(
        success=False,
        stderr=(
            'File "/tmp/scene.py", line 5\n'
            "TypeError: Scene.play() got an unexpected keyword argument 'bad'\n"
            "Manim validation timed out after 120s"
        ),
        stdout="",
        temp_dir=None,
    )
    pass_render = ManimRenderResult(success=True, stderr="", stdout="", temp_dir=None)
    llm = MagicMock()
    llm.complete.return_value = (
        '{"can_fix": true, "original_code": "bad_call", '
        '"replacement_code": "good_call", "explanation": "remove bad keyword"}'
    )

    with patch(
        "app.review_loop.render_manim_for_validation",
        side_effect=[timeout_render, pass_render],
    ):
        result = _make_loop(llm).run("header\nbad_call\nfooter", CODE_REVIEW_CONFIG)

    assert result.passed is True
    assert result.iterations[0].outcome == "resolved"
    assert "Validation LLM error" not in (result.iterations[0].error_summary or "")
    prompt = llm.complete.call_args.kwargs["messages"][1]["content"]
    assert "TypeError: Scene.play()" in prompt


def test_direct_manim_timeout_is_not_classified_as_an_llm_failure() -> None:
    from app.renderer import ManimProcessTimeout

    llm = MagicMock()
    llm.complete.return_value = (
        '{"can_fix": true, "original_code": "bad_call", '
        '"replacement_code": "good_call", "explanation": "fix call"}'
    )
    pass_render = ManimRenderResult(success=True, stderr="", stdout="", temp_dir=None)
    timeout = ManimProcessTimeout(
        120,
        stdout="",
        stderr='File "/tmp/scene.py", line 2\nTypeError: wrong call',
    )

    with patch(
        "app.review_loop.render_manim_for_validation",
        side_effect=[timeout, pass_render],
    ):
        result = _make_loop(llm).run("header\nbad_call\nfooter", CODE_REVIEW_CONFIG)

    assert result.passed is True
    assert result.iterations[0].outcome == "resolved"


def test_review_loop_reports_model_attempt_and_exact_replacement() -> None:
    fail_render = ManimRenderResult(
        success=False,
        stderr='File "scene.py", line 5\nNameError: bad',
        stdout="",
        temp_dir=None,
    )
    pass_render = ManimRenderResult(success=True, stderr="", stdout="", temp_dir=None)
    llm = MagicMock()
    llm.complete.return_value = (
        '{"can_fix": true, "original_code": "bad_line", "replacement_code": "good_line", '
        '"explanation": "fixed"}'
    )
    stages: list[dict] = []

    with patch("app.review_loop.render_manim_for_validation", side_effect=[fail_render, pass_render]):
        result = _make_loop(llm).run(
            "before\nbad_line\nafter", CODE_REVIEW_CONFIG, on_stage=stages.append
        )

    assert any(stage["phase"] == "fixing" and stage["model"] == "test-model" for stage in stages)
    patch_stage = next(stage for stage in stages if stage["phase"] == "patch_applied")
    assert patch_stage["original_code"] == "bad_line"
    assert patch_stage["replacement_code"] == "good_line"
    assert result.iterations[0].original_code == "bad_line"


def test_review_loop_rejects_a_full_file_reviewer_response_without_mutating_code() -> None:
    fail_render = ManimRenderResult(
        success=False,
        stderr='File "scene.py", line 2\nNameError: bad',
        stdout="",
        temp_dir=None,
    )
    source = "line_one\nbad_line\nline_three\n"
    llm = MagicMock()
    llm.complete.return_value = (
        '{"can_fix": true, "original_code": "line_one\\nbad_line\\nline_three\\n", '
        '"replacement_code": "rewritten_file", "explanation": "rewrite"}'
    )
    stages: list[dict] = []

    with patch("app.review_loop.render_manim_for_validation", return_value=fail_render):
        result = _make_loop(llm).run(source, CODE_REVIEW_CONFIG, on_stage=stages.append)

    assert result.manim_code == source
    assert any(stage["phase"] == "patch_rejected" for stage in stages)
    assert all(iteration.original_code is None for iteration in result.iterations)


def test_review_loop_escalates_on_same_error() -> None:
    """If the same error persists after a fix, the loop should escalate."""
    from app.models import ModelTier

    tiers = [
        ModelTier(model="weak", max_attempts=1),
        ModelTier(model="strong", max_attempts=1),
    ]
    fail_render = ManimRenderResult(
        success=False,
        stderr='File "scene.py", line 10\nNameError: oops',
        stdout="",
        temp_dir=None,
    )

    llm = MagicMock()
    llm.complete.return_value = (
        '{"can_fix": true, "original_code": "x", "replacement_code": "y", "explanation": "try"}'
    )

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
        success=False,
        stderr='File "scene.py", line 1\nSyntaxError: bad',
        stdout="",
        temp_dir=None,
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
    assert "as JSON `\\n`." in CODE_REVIEW_CONFIG.fix_prompt
    assert "as JSON `\\n`." in VISUAL_REVIEW_CONFIG.fix_prompt


def test_visual_reviewer_invalid_verdict_is_not_treated_as_pass() -> None:
    llm = MagicMock()
    llm.complete_with_image.return_value = "not-json"

    with pytest.raises(ValueError, match="invalid has_issues verdict"):
        _make_loop(llm)._vlm_analyse_frame(
            b"png",
            "from manim import *",
            VISUAL_REVIEW_CONFIG,
            "test-model",
        )


def test_review_model_tiers_are_ordered_without_duplicates() -> None:
    from app.models import load_review_loop_tiers

    tiers = load_review_loop_tiers()
    assert [tier.model for tier in tiers] == [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
    ]
    assert tiers[-1].max_attempts >= 1


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


def test_semantic_strategy_fingerprint_ignores_formatting() -> None:
    assert semantic_strategy_fingerprint("value=1", "value=2") == semantic_strategy_fingerprint(
        "value = 1", "value = 2"
    )


def test_semantic_strategy_fingerprint_detects_same_api_rename_in_different_wrappers() -> None:
    assert semantic_strategy_fingerprint(
        "self.play(ShowCreation(circle))", "self.play(Create(circle))"
    ) == semantic_strategy_fingerprint(
        "self.add(ShowCreation(square))", "self.add(Create(square))"
    )


def test_reviewer_requires_a_boolean_can_fix_verdict() -> None:
    fail_render = ManimRenderResult(
        success=False,
        stderr='File "scene.py", line 2\nNameError: bad',
        stdout="",
        temp_dir=None,
    )
    llm = MagicMock()
    llm.complete.return_value = (
        '{"can_fix": "false", "original_code": "", '
        '"replacement_code": "", "explanation": "not a boolean"}'
    )
    with patch("app.review_loop.render_manim_for_validation", return_value=fail_render):
        result = _make_loop(llm).run("header\nbad\n", CODE_REVIEW_CONFIG)

    assert result.passed is False
    assert result.iterations[0].outcome == "invalid_reviewer_response"


def test_reviewer_gets_one_format_repair_before_escalation() -> None:
    from app.models import ModelTier

    fail_render = ManimRenderResult(
        success=False,
        stderr='File "scene.py", line 2\nNameError: bad',
        stdout="",
    )
    success = ManimRenderResult(success=True, stderr="", stdout="")
    malformed = (
        '{"can_fix": true, "original_code": "bad_line", '
        '"replacement_code": "good_line"}'
    )
    normalized = (
        '{"can_fix": true, "original_code": "bad_line", '
        '"replacement_code": "good_line", "explanation": "fixed"}'
    )
    llm = MagicMock()
    llm.complete.side_effect = [malformed, normalized]

    with (
        patch(
            "app.review_loop.render_manim_for_validation",
            side_effect=[fail_render, success],
        ),
        patch("app.review_loop.build_runtime_api_context", return_value=None),
    ):
        result = ReviewLoop(
            llm=llm,
            tiers=[ModelTier(model="format-model", max_attempts=1)],
        ).run("header\nbad_line\nfooter", CODE_REVIEW_CONFIG)

    assert result.passed is True
    assert result.manim_code == "header\ngood_line\nfooter"
    assert llm.complete.call_count == 2
    normalization_call = llm.complete.call_args_list[1]
    assert normalization_call.kwargs["temperature"] == 0
    assert malformed in normalization_call.kwargs["messages"][1]["content"]


def test_reviewer_selects_the_schema_valid_object_from_multiple_objects() -> None:
    raw = (
        '{"note": "analysis metadata"}\n'
        '{"can_fix": true, "original_code": "bad", '
        '"replacement_code": "good", "explanation": "valid fix"}'
    )

    fix = ReviewLoop._decode_code_fix(raw)

    assert fix is not None
    assert fix.original_code == "bad"
    assert fix.replacement_code == "good"


def test_runtime_api_context_is_injected_and_audited_before_fix() -> None:
    fail_render = ManimRenderResult(
        success=False,
        stderr='File "/tmp/scene.py", line 4\nNameError: name \'ShowCreation\' is not defined',
        stdout="",
    )
    pass_render = ManimRenderResult(success=True, stderr="", stdout="")
    runtime_context = {
        "manim_version": "0.19.2",
        "python_executable": "/runtime/python",
        "target_symbol": "ShowCreation",
        "exact_api": {"symbol": "ShowCreation", "exists": False},
        "alternatives": [
            {
                "symbol": "Create",
                "exists": True,
                "signature": "(mobject)",
                "summary": "Incrementally show a VMobject.",
                "example": "self.play(Create(mobject))",
            }
        ],
    }
    llm = MagicMock()
    llm.complete.return_value = (
        '{"can_fix": true, "original_code": "ShowCreation", '
        '"replacement_code": "Create", "explanation": "runtime rename"}'
    )
    stages: list[dict] = []
    code = "from manim import *\nclass GeneratedScene(Scene):\n def construct(self):\n  self.play(ShowCreation(Circle()))\n"

    with (
        patch("app.review_loop.render_manim_for_validation", side_effect=[fail_render, pass_render]),
        patch("app.review_loop.build_runtime_api_context", return_value=runtime_context),
    ):
        result = _make_loop(llm).run(code, CODE_REVIEW_CONFIG, on_stage=stages.append)

    prompt = llm.complete.call_args.kwargs["messages"][1]["content"]
    assert "<RUNTIME_MANIM_API_CONTEXT>" in prompt
    assert "Manim version: 0.19.2" in prompt
    assert "Signature: (mobject)" in prompt
    assert result.iterations[0].runtime_api_context == runtime_context
    assert any(stage["phase"] == "runtime_api_context" for stage in stages)


def test_repair_memory_reaches_stronger_model_and_guard_blocks_semantic_duplicate() -> None:
    from app.models import ModelTier

    tiers = [ModelTier(model="weak", max_attempts=1), ModelTier(model="strong", max_attempts=1)]
    fail_render = ManimRenderResult(
        success=False,
        stderr='File "/tmp/scene.py", line 2\nNameError: name \'bad\' is not defined',
        stdout="",
    )
    llm = MagicMock()
    llm.complete.side_effect = [
        '{"can_fix": true, "original_code": "value = 1", '
        '"replacement_code": "value=2", "explanation": "first strategy"}',
        '{"can_fix": true, "original_code": "value = 1", '
        '"replacement_code": "value = 2", "explanation": "same strategy reformatted"}',
    ]
    source = "header\nvalue = 1\nline3\nline4\nline5\nline6\nline7\nline8\n"

    with (
        patch("app.review_loop.render_manim_for_validation", return_value=fail_render) as render,
        patch("app.review_loop.build_runtime_api_context", return_value=None),
    ):
        result = ReviewLoop(llm=llm, tiers=tiers).run(source, CODE_REVIEW_CONFIG)

    second_prompt = llm.complete.call_args_list[1].kwargs["messages"][1]["content"]
    assert "<REPAIR_ATTEMPT_MEMORY>" in second_prompt
    assert "first strategy" in second_prompt
    assert result.iterations[1].strategy_guard_triggered is True
    assert result.iterations[1].outcome == "duplicate_strategy"
    assert result.manim_code == source
    assert render.call_count == 2  # cached episode + duplicate strategy are not rendered again


def test_repair_memory_resets_after_advancing_to_a_new_error() -> None:
    from app.models import ModelTier

    error_a = ManimRenderResult(
        success=False,
        stderr='File "/tmp/scene.py", line 2\nNameError: name \'bad_a\' is not defined',
        stdout="",
    )
    error_b = ManimRenderResult(
        success=False,
        stderr='File "/tmp/scene.py", line 3\nNameError: name \'bad_b\' is not defined',
        stdout="",
    )
    success = ManimRenderResult(success=True, stderr="", stdout="")
    llm = MagicMock()
    llm.complete.side_effect = [
        '{"can_fix": true, "original_code": "bad_a", '
        '"replacement_code": "fixed_a", "explanation": "fix error A"}',
        '{"can_fix": true, "original_code": "bad_b", '
        '"replacement_code": "fixed_b", "explanation": "fix error B"}',
    ]
    stages: list[dict] = []
    source = "header\nbad_a\nbad_b\nline4\nline5\nline6\nline7\nline8\n"

    with (
        patch(
            "app.review_loop.render_manim_for_validation",
            side_effect=[error_a, error_b, success],
        ),
        patch("app.review_loop.build_runtime_api_context", return_value=None),
    ):
        result = ReviewLoop(
            llm=llm, tiers=[ModelTier(model="one-model", max_attempts=2)]
        ).run(source, CODE_REVIEW_CONFIG, on_stage=stages.append)

    second_prompt = llm.complete.call_args_list[1].kwargs["messages"][1]["content"]
    assert "<REPAIR_ATTEMPT_MEMORY>" not in second_prompt
    assert "fix error A" not in second_prompt
    assert result.passed is True
    assert result.iterations[0].outcome == "advanced_to_new_error"
    assert result.iterations[1].repair_history_count == 0
    assert any(stage["phase"] == "repair_memory_reset" for stage in stages)
    assert [stage["error_episode"] for stage in stages if stage["phase"] == "error_episode_started"] == [1, 2]


def test_new_error_episode_uses_new_traceback_and_current_source_without_rerender() -> None:
    """Regression: CENTER is fixed before FileNotFoundError becomes actionable."""
    from app.models import ModelTier

    center_error = ManimRenderResult(
        success=False,
        stderr=(
            'File "/tmp/scene.py", line 2\n'
            "NameError: name 'CENTER' is not defined"
        ),
        stdout="",
    )
    file_error = ManimRenderResult(
        success=False,
        stderr=(
            'File "/tmp/scene.py", line 3\n'
            "FileNotFoundError: assets/chart.csv"
        ),
        stdout="",
    )
    success = ManimRenderResult(success=True, stderr="", stdout="")
    llm = MagicMock()
    llm.complete.side_effect = [
        (
            '{"can_fix": true, "original_code": "aligned_edge=CENTER", '
            '"replacement_code": "aligned_edge=ORIGIN", '
            '"explanation": "replace invalid CENTER"}'
        ),
        (
            '{"can_fix": true, "original_code": "load(\\"assets/chart.csv\\")", '
            '"replacement_code": "load_optional(\\"assets/chart.csv\\")", '
            '"explanation": "handle the missing asset"}'
        ),
    ]
    source = (
        "header\n"
        "aligned_edge=CENTER\n"
        'load("assets/chart.csv")\n'
        "line4\nline5\nline6\nline7\nline8\n"
    )

    with (
        patch(
            "app.review_loop.render_manim_for_validation",
            side_effect=[center_error, file_error, success],
        ) as render,
        patch("app.review_loop.build_runtime_api_context", return_value=None),
    ):
        result = ReviewLoop(
            llm=llm,
            tiers=[ModelTier(model="one-model", max_attempts=3)],
        ).run(source, CODE_REVIEW_CONFIG, max_attempts=3)

    second_prompt = llm.complete.call_args_list[1].kwargs["messages"][1]["content"]
    assert "FileNotFoundError: assets/chart.csv" in second_prompt
    assert "aligned_edge=ORIGIN" in second_prompt
    assert "name 'CENTER' is not defined" not in second_prompt
    assert 'number="2"' in second_prompt
    assert result.passed is True
    assert result.total_attempts == 2
    assert render.call_count == 3


def test_configured_attempt_cap_matches_actual_reviewer_requests() -> None:
    from app.models import ModelTier

    persistent_error = ManimRenderResult(
        success=False,
        stderr='File "/tmp/scene.py", line 2\nNameError: bad',
        stdout="",
    )
    llm = MagicMock()
    llm.complete.side_effect = [
        (
            '{"can_fix": true, "original_code": "header", '
            f'"replacement_code": "header_{attempt}", '
            f'"explanation": "strategy {attempt}"}}'
        )
        for attempt in range(1, 4)
    ]
    source = "header\nbad\nline3\nline4\nline5\nline6\nline7\nline8\n"

    with (
        patch(
            "app.review_loop.render_manim_for_validation",
            return_value=persistent_error,
        ),
        patch("app.review_loop.build_runtime_api_context", return_value=None),
    ):
        result = ReviewLoop(
            llm=llm,
            tiers=[ModelTier(model="one-model", max_attempts=5)],
        ).run(source, CODE_REVIEW_CONFIG, max_attempts=3)

    assert result.passed is False
    assert result.total_attempts == 3
    assert llm.complete.call_count == 3
    assert len(result.iterations) == 3


def test_revalidation_exception_keeps_patch_for_the_next_tier() -> None:
    from app.models import ModelTier

    error_a = ManimRenderResult(
        success=False,
        stderr='File "/tmp/scene.py", line 2\nNameError: name \'bad_a\' is not defined',
        stdout="",
    )
    error_b = ManimRenderResult(
        success=False,
        stderr='File "/tmp/scene.py", line 3\nNameError: name \'bad_b\' is not defined',
        stdout="",
    )
    success = ManimRenderResult(success=True, stderr="", stdout="")
    llm = MagicMock()
    llm.complete.side_effect = [
        '{"can_fix": true, "original_code": "bad_a", '
        '"replacement_code": "fixed_a", "explanation": "fix A"}',
        '{"can_fix": true, "original_code": "bad_b", '
        '"replacement_code": "fixed_b", "explanation": "fix B"}',
    ]
    tiers = [
        ModelTier(model="weak", max_attempts=1),
        ModelTier(model="strong", max_attempts=1),
    ]
    source = "header\nbad_a\nbad_b\nline4\nline5\nline6\nline7\nline8\n"

    with (
        patch(
            "app.review_loop.render_manim_for_validation",
            side_effect=[error_a, RuntimeError("renderer unavailable"), error_b, success],
        ),
        patch("app.review_loop.build_runtime_api_context", return_value=None),
    ):
        result = ReviewLoop(llm=llm, tiers=tiers).run(source, CODE_REVIEW_CONFIG)

    assert result.passed is True
    assert "fixed_a" in result.manim_code
    assert "fixed_b" in result.manim_code
    assert "bad_a" not in result.manim_code
    assert "bad_b" not in result.manim_code
    assert result.iterations[0].outcome == "advanced_to_new_error"
    assert result.iterations[1].outcome == "resolved"


def test_transient_revalidation_error_retries_same_tier_checkpoint() -> None:
    from app.models import ModelTier

    error_a = ManimRenderResult(
        success=False,
        stderr='File "/tmp/scene.py", line 2\nNameError: bad_a',
        stdout="",
    )
    success = ManimRenderResult(success=True, stderr="", stdout="")
    llm = MagicMock()
    llm.complete.return_value = (
        '{"can_fix": true, "original_code": "bad_a", '
        '"replacement_code": "fixed_a", "explanation": "fix A"}'
    )

    with (
        patch(
            "app.review_loop.render_manim_for_validation",
            side_effect=[error_a, RuntimeError("temporary renderer failure"), success],
        ),
        patch("app.review_loop.build_runtime_api_context", return_value=None),
    ):
        result = ReviewLoop(
            llm=llm,
            tiers=[ModelTier(model="one-model", max_attempts=2)],
        ).run("header\nbad_a\nfooter", CODE_REVIEW_CONFIG)

    assert result.passed is True
    assert result.total_attempts == 1
    assert result.manim_code == "header\nfixed_a\nfooter"
    assert result.iterations[0].outcome == "resolved"
    assert llm.complete.call_count == 1


def test_checkpoint_rolls_back_only_when_same_error_is_confirmed() -> None:
    from app.models import ModelTier

    error_a = ManimRenderResult(
        success=False,
        stderr='File "/tmp/scene.py", line 2\nNameError: bad_a',
        stdout="",
    )
    success = ManimRenderResult(success=True, stderr="", stdout="")
    llm = MagicMock()
    llm.complete.side_effect = [
        '{"can_fix": true, "original_code": "bad_a", '
        '"replacement_code": "wrong_a", "explanation": "wrong fix"}',
        '{"can_fix": true, "original_code": "bad_a", '
        '"replacement_code": "fixed_a", "explanation": "correct fix"}',
    ]

    with (
        patch(
            "app.review_loop.render_manim_for_validation",
            side_effect=[
                error_a,
                RuntimeError("temporary renderer failure"),
                error_a,
                success,
            ],
        ),
        patch("app.review_loop.build_runtime_api_context", return_value=None),
    ):
        result = ReviewLoop(
            llm=llm,
            tiers=[ModelTier(model="one-model", max_attempts=2)],
        ).run("header\nbad_a\nfooter", CODE_REVIEW_CONFIG)

    assert result.passed is True
    assert result.manim_code == "header\nfixed_a\nfooter"
    assert "wrong_a" not in result.manim_code
    assert result.iterations[0].outcome == "same_error"
    assert result.iterations[0].same_error is True
    assert result.iterations[1].outcome == "resolved"
    second_prompt = llm.complete.call_args_list[1].kwargs["messages"][1]["content"]
    assert "wrong fix" in second_prompt


def test_exhausted_unvalidated_checkpoint_reports_infrastructure_error() -> None:
    from app.models import ModelTier

    error_a = ManimRenderResult(
        success=False,
        stderr='File "/tmp/scene.py", line 2\nNameError: bad_a',
        stdout="",
    )
    llm = MagicMock()
    llm.complete.return_value = (
        '{"can_fix": true, "original_code": "bad_a", '
        '"replacement_code": "candidate_a", "explanation": "candidate fix"}'
    )

    with (
        patch(
            "app.review_loop.render_manim_for_validation",
            side_effect=[error_a, RuntimeError("renderer unavailable")],
        ),
        patch("app.review_loop.build_runtime_api_context", return_value=None),
    ):
        result = ReviewLoop(
            llm=llm,
            tiers=[ModelTier(model="one-model", max_attempts=1)],
        ).run("header\nbad_a\nfooter", CODE_REVIEW_CONFIG)

    assert result.passed is False
    assert result.manim_code == "header\ncandidate_a\nfooter"
    assert result.iterations[0].outcome == "candidate_unvalidated"
    assert "renderer unavailable" in (result.final_error or "")


def test_code_validation_exception_is_not_mislabeled_as_llm_error() -> None:
    from app.models import ModelTier

    with patch(
        "app.review_loop.render_manim_for_validation",
        side_effect=OSError("cannot start renderer"),
    ):
        result = ReviewLoop(
            llm=MagicMock(),
            tiers=[ModelTier(model="one-model", max_attempts=1)],
        ).run("code", CODE_REVIEW_CONFIG)

    assert result.passed is False
    assert result.iterations[0].outcome == "validation_error"
    assert "renderer error" in (result.iterations[0].error_summary or "").lower()
    assert "llm error" not in (result.iterations[0].error_summary or "").lower()
    assert "cannot start renderer" in (result.final_error or "")


def test_same_message_at_a_later_source_location_is_a_new_error() -> None:
    from app.models import ModelTier

    first_location = ManimRenderResult(
        success=False,
        stderr='File "/tmp/scene.py", line 2\nNameError: name \'foo\' is not defined',
        stdout="",
    )
    second_location = ManimRenderResult(
        success=False,
        stderr='File "/tmp/scene.py", line 3\nNameError: name \'foo\' is not defined',
        stdout="",
    )
    success = ManimRenderResult(success=True, stderr="", stdout="")
    llm = MagicMock()
    llm.complete.side_effect = [
        '{"can_fix": true, "original_code": "foo(first)", '
        '"replacement_code": "fixed(first)", "explanation": "fix first call"}',
        '{"can_fix": true, "original_code": "foo(second)", '
        '"replacement_code": "fixed(second)", "explanation": "fix second call"}',
    ]
    source = "header\nfoo(first)\nfoo(second)\nline4\nline5\nline6\nline7\nline8\n"

    with (
        patch(
            "app.review_loop.render_manim_for_validation",
            side_effect=[first_location, second_location, success],
        ),
        patch("app.review_loop.build_runtime_api_context", return_value=None),
    ):
        result = ReviewLoop(
            llm=llm, tiers=[ModelTier(model="one-model", max_attempts=2)]
        ).run(source, CODE_REVIEW_CONFIG)

    assert result.passed is True
    assert result.manim_code.count("fixed(") == 2
    assert result.iterations[0].outcome == "advanced_to_new_error"
    assert result.iterations[0].error_fingerprint != result.iterations[1].error_fingerprint


def test_same_error_line_drift_from_a_patch_is_not_treated_as_progress() -> None:
    from app.models import ModelTier

    old_line = ManimRenderResult(
        success=False,
        stderr='File "/tmp/scene.py", line 2\nNameError: name \'bad\' is not defined',
        stdout="",
    )
    shifted_line = ManimRenderResult(
        success=False,
        stderr='File "/tmp/scene.py", line 3\nNameError: name \'bad\' is not defined',
        stdout="",
    )
    llm = MagicMock()
    llm.complete.return_value = (
        '{"can_fix": true, "original_code": "header", '
        '"replacement_code": "header\\nextra", "explanation": "unrelated edit"}'
    )
    source = "header\nbad\nline3\nline4\nline5\nline6\nline7\nline8\n"

    with (
        patch(
            "app.review_loop.render_manim_for_validation",
            side_effect=[old_line, shifted_line],
        ),
        patch("app.review_loop.build_runtime_api_context", return_value=None),
    ):
        result = ReviewLoop(
            llm=llm, tiers=[ModelTier(model="one-model", max_attempts=1)]
        ).run(source, CODE_REVIEW_CONFIG)

    assert result.passed is False
    assert result.manim_code == source
    assert result.iterations[0].outcome == "same_error"
