from __future__ import annotations

import pytest
from ai_engine.builder_loop import (
    _agent_has_blocking, _code_review_passed, _visual_review_passed,
    truncate_error_logs, _get_convergence_timestamp, _run_agent_with_self_correction
)
from shared.constants import SeverityLevel
from shared.schemas.review import ReviewIssue, ReviewResult
from ai_engine.config import BuilderReviewLoopConfig

@pytest.fixture
def base_cfg():
    return BuilderReviewLoopConfig(
        max_rounds=3,
        early_stop_require_all=("code_review_passed",),
        code_agent_blocking_issues_empty=True,
        code_static_ast_parse_ok=True,
        code_static_forbidden_imports_ok=True,
        visual_agent_blocking_issues_empty=True,
        visual_reviewer_enabled=True,
        blocking_severity_min="warning",
        stop_when_only_info_severity=False,
        on_max_rounds_exceeded="fail",
    )

def test_agent_has_blocking_severity(base_cfg):
    issues = [ReviewIssue(severity=SeverityLevel.ERROR, code="E", message="err")]
    assert _agent_has_blocking(issues, base_cfg) is True
    
    issues = [ReviewIssue(severity=SeverityLevel.INFO, code="I", message="info")]
    assert _agent_has_blocking(issues, base_cfg) is False

def test_agent_has_blocking_info_stop(base_cfg):
    from dataclasses import replace
    cfg = replace(base_cfg, stop_when_only_info_severity=True)
    issues = [ReviewIssue(severity=SeverityLevel.INFO, code="I", message="info")]
    assert _agent_has_blocking(issues, cfg) is True

def test_code_review_passed_variants(base_cfg):
    res = ReviewResult(issues=[])
    assert _code_review_passed(cfg=base_cfg, syntax_ok=True, policy_ok=True, agent_result=res) is True
    assert _code_review_passed(cfg=base_cfg, syntax_ok=False, policy_ok=True, agent_result=res) is False
    
    # Test agent blocking
    res_err = ReviewResult(issues=[ReviewIssue(severity="error", code="X", message="!")])
    assert _code_review_passed(cfg=base_cfg, syntax_ok=True, policy_ok=True, agent_result=res_err) is False

def test_visual_review_passed_variants(base_cfg):
    res = ReviewResult(issues=[])
    assert _visual_review_passed(cfg=base_cfg, agent_result=res) is True
    
    res_err = ReviewResult(issues=[ReviewIssue(severity="error", code="X", message="!")])
    assert _visual_review_passed(cfg=base_cfg, agent_result=res_err) is False
    
    # If not checking blocking
    from dataclasses import replace
    cfg_no_check = replace(base_cfg, visual_agent_blocking_issues_empty=False)
    assert _visual_review_passed(cfg=cfg_no_check, agent_result=res_err) is True


def test_truncate_error_logs():
    assert truncate_error_logs("short") == "short"
    long_str = "A" * 3000
    truncated = truncate_error_logs(long_str, max_chars=100)
    assert "[TRUNCATED]" in truncated
    assert len(truncated) <= 120 # roughly

def test_get_convergence_timestamp():
    assert _get_convergence_timestamp(None) is None
    sync = {"version": "2", "granularity": "segment", "segments": [{"start": 0, "end": 10.5, "text": "test"}]}
    assert _get_convergence_timestamp(sync) == 10.5
    
    # invalid
    assert _get_convergence_timestamp("invalid") is None

@pytest.mark.anyio
async def test_run_agent_with_self_correction_success():
    async def ok_call(result, **kwargs):
        return result, "v1", {}, "sys", "usr"
    
    # No schema
    res, v, m, s, u = await _run_agent_with_self_correction("test", ok_call, None, result="plain text")
    assert res == "plain text"
    
    # With schema, result is str
    from pydantic import BaseModel
    class MySchema(BaseModel):
        foo: str
    
    res, v, m, s, u = await _run_agent_with_self_correction("test", ok_call, MySchema, result='{"foo": "bar"}')
    assert res.foo == "bar"
    
    # With schema, result is dict
    res, v, m, s, u = await _run_agent_with_self_correction("test", ok_call, MySchema, result={"foo": "baz"})
    assert res.foo == "baz"
    
    # With schema, result is already schema instance
    inst = MySchema(foo="qux")
    res, v, m, s, u = await _run_agent_with_self_correction("test", ok_call, MySchema, result=inst)
    assert res is inst

@pytest.mark.anyio
async def test_run_agent_with_self_correction_fail():
    async def fail_call(**kwargs):
        raise ValueError("LLM fail")
    
    with pytest.raises(ValueError, match="LLM fail"):
        await _run_agent_with_self_correction("test", fail_call, None)
