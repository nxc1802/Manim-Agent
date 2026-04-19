from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from backend.services.code_sandbox import SandboxLimits, static_check_split
from shared.schemas.review import ReviewIssue, ReviewResult
from shared.schemas.review_pipeline import ReviewRoundResponse

from ai_engine.agents.code_reviewer import run_code_reviewer
from ai_engine.agents.visual_reviewer import run_visual_reviewer
from ai_engine.config import AgentLLMParams, BuilderReviewLoopConfig, RuntimeLimitsConfig
from ai_engine.llm_client import LLMClient

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2, "blocker": 3}


def _severity_at_least(sev: str, minimum: str) -> bool:
    return _SEVERITY_RANK.get(sev, 0) >= _SEVERITY_RANK.get(minimum, 1)


def _agent_has_blocking(issues: list[ReviewIssue], cfg: BuilderReviewLoopConfig) -> bool:
    for issue in issues:
        if _severity_at_least(issue.severity, cfg.blocking_severity_min):
            return True
        if cfg.stop_when_only_info_severity and issue.severity == "info":
            return True
    return False


def _code_review_passed(
    *,
    cfg: BuilderReviewLoopConfig,
    syntax_ok: bool,
    policy_ok: bool,
    agent_result: ReviewResult,
) -> bool:
    ok = True
    if cfg.code_static_ast_parse_ok:
        ok = ok and syntax_ok
    if cfg.code_static_forbidden_imports_ok:
        ok = ok and policy_ok
    if cfg.code_agent_blocking_issues_empty:
        ok = ok and not _agent_has_blocking(agent_result.issues, cfg)
    return ok


def _visual_review_passed(*, cfg: BuilderReviewLoopConfig, agent_result: ReviewResult) -> bool:
    if not cfg.visual_agent_blocking_issues_empty:
        return True
    return not _agent_has_blocking(agent_result.issues, cfg)


def run_single_review_round(
    *,
    llm: LLMClient,
    review_cfg: BuilderReviewLoopConfig,
    code_llm: AgentLLMParams,
    visual_llm: AgentLLMParams,
    manim_code: str,
    sandbox_limits: SandboxLimits,
    preview_video_path: Path | None,
    extract_preview_frame: Callable[[Path], bytes],
    runtime_limits: RuntimeLimitsConfig | None = None,
) -> ReviewRoundResponse:
    """Phase 8 — single round: static + Code Reviewer first; Visual only after code passes.

    Early stop is **true** only when both code and visual branches pass configured criteria
    (AND). If code fails or preview is missing, visual review is skipped.
    """
    rt = runtime_limits or RuntimeLimitsConfig(
        worker_man_render_timeout_seconds=3600,
        worker_tts_subprocess_timeout_seconds=900,
        preview_poll_timeout_seconds=900,
        preview_poll_interval_seconds=0.5,
        llm_timeout_default_seconds=600,
        llm_timeouts={},
    )
    syntax_ok, policy_ok, _err = static_check_split(manim_code, limits=sandbox_limits)
    empty = ReviewResult(issues=[])
    metrics: dict[str, Any] = {}
    if not manim_code.strip():
        return ReviewRoundResponse(
            static_parse_ok=syntax_ok,
            static_imports_ok=policy_ok,
            code_review=empty,
            code_review_passed=False,
            visual_review=None,
            visual_review_skipped_reason="empty_code",
            visual_review_passed=None,
            early_stop=False,
            metrics=metrics,
        )

    code_review, _pv, cm = run_code_reviewer(
        llm=llm,
        model=code_llm.model,
        temperature=code_llm.temperature,
        max_tokens=code_llm.max_tokens,
        manim_code=manim_code,
        request_timeout_seconds=rt.llm_timeout_seconds("code_reviewer"),
    )
    metrics["code_reviewer"] = cm
    code_passed = _code_review_passed(
        cfg=review_cfg,
        syntax_ok=syntax_ok,
        policy_ok=policy_ok,
        agent_result=code_review,
    )

    visual_review: ReviewResult | None = None
    visual_passed: bool | None = None
    skip_reason: str | None = None

    if not code_passed:
        skip_reason = "code_review_not_passed"
    elif preview_video_path is None or not preview_video_path.is_file():
        skip_reason = "no_preview_video"
    else:
        try:
            frame_jpeg = extract_preview_frame(preview_video_path)
            visual_review, _pv2, vm = run_visual_reviewer(
                llm=llm,
                model=visual_llm.model,
                temperature=visual_llm.temperature,
                max_tokens=visual_llm.max_tokens,
                frame_jpeg=frame_jpeg,
                context=(
                    "Frame is the last decoded frame of the preview (approx. Scene.play() end)."
                ),
                request_timeout_seconds=rt.llm_timeout_seconds("visual_reviewer"),
            )
            metrics["visual_reviewer"] = vm
            visual_passed = _visual_review_passed(cfg=review_cfg, agent_result=visual_review)
        except Exception:
            logger.exception("Visual review failed")
            visual_review = ReviewResult(
                issues=[
                    ReviewIssue(
                        severity="error",
                        code="visual_pipeline_error",
                        message="Visual review raised an exception",
                    ),
                ],
            )
            visual_passed = False
            skip_reason = "visual_review_error"

    early_stop = bool(code_passed and visual_passed is True)
    return ReviewRoundResponse(
        static_parse_ok=syntax_ok,
        static_imports_ok=policy_ok,
        code_review=code_review,
        code_review_passed=code_passed,
        visual_review=visual_review,
        visual_review_skipped_reason=skip_reason,
        visual_review_passed=visual_passed,
        early_stop=early_stop,
        metrics=metrics,
    )
