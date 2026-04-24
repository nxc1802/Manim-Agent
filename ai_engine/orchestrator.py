from __future__ import annotations

import base64
import hashlib
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypeVar
from uuid import UUID, uuid4

from backend.core.config import settings
from backend.services.code_sandbox import (
    SandboxLimits,
    SandboxValidationError,
    static_check_split,
    validate_manim_code,
)
from backend.services.frame_info import (
    extract_frame_at_timestamp,
)
from backend.services.job_wait import wait_for_render_job
from backend.services.supabase_pipeline_rest import insert_pipeline_run_row
from backend.services.supabase_storage_rest import upload_preview_frame_and_sign
from backend.services.sync_engine_logic import validate_sync_duration
from pydantic import BaseModel
from shared.pipeline_log import pipeline_event
from shared.schemas.planner_output import PlannerOutput
from shared.schemas.review import ReviewIssue, ReviewResult
from shared.schemas.review_pipeline import ReviewRoundResponse
from shared.schemas.scene import Scene
from worker.tasks import render_manim_scene

from ai_engine.agents.builder import run_builder
from ai_engine.agents.code_reviewer import run_code_reviewer
from ai_engine.agents.director import run_director
from ai_engine.agents.planner import run_planner
from ai_engine.agents.visual_reviewer import run_visual_reviewer
from ai_engine.config import (
    AgentLLMParams,
    BuilderReviewLoopConfig,
    RuntimeLimitsConfig,
    load_builder_review_loop,
    resolve_agent_params,
)
from ai_engine.json_utils import parse_json_object
from ai_engine.llm_client import LLMClient

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="BaseModel")

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


def _get_convergence_timestamp(sync_segments: dict[str, Any] | None) -> float | None:
    """Information Convergence Point: End of the last narration segment."""
    if not sync_segments:
        return None
    try:
        from shared.schemas.voice_segments import VoiceSegmentTimestamps
        if isinstance(sync_segments, dict):
            sync = VoiceSegmentTimestamps.model_validate(sync_segments)
        else:
            sync = sync_segments # type: ignore
        
        if sync.segments:
            return sync.segments[-1].end
    except Exception:
        logger.warning("Failed to parse sync_segments for convergence point")
    return None


def _run_agent_with_self_correction(
    agent_name: str,
    call_fn: Callable[..., Any],
    schema: type[T] | None,
    max_retries: int = 3,
    **kwargs: Any
) -> tuple[Any, str, dict[str, Any]]:
    """Helper to retry agent calls if they produce invalid JSON or fail validation.
    
    Returns: (result, prompt_version, total_metrics)
    """
    history: list[dict[str, str]] = []
    last_error: str | None = None
    total_metrics = {"prompt_tokens": 0, "completion_tokens": 0, "duration_ms": 0}

    for attempt in range(1, max_retries + 1):
        try:
            if "chat_history" in kwargs:
                kwargs["chat_history"] = history
            
            if last_error:
                if agent_name == "planner":
                    kwargs["storyboard_text"] = (
                        f"{kwargs.get('storyboard_text', '')}\n\n"
                        f"[SELF-CORRECTION] Previous output was invalid: {last_error}. "
                        "Please fix the JSON structure and ensure it matches the schema."
                    )
                elif agent_name == "director":
                    kwargs["extra_brief"] = (
                        f"{kwargs.get('extra_brief') or ''}\n\n"
                        f"[SELF-CORRECTION] Previous output was invalid: {last_error}. "
                        "Please fix and retry."
                    )

            result, version, metrics = call_fn(**kwargs)
            
            # Accumulate metrics
            total_metrics["prompt_tokens"] += metrics.get("prompt_tokens") or 0
            total_metrics["completion_tokens"] += metrics.get("completion_tokens") or 0
            total_metrics["duration_ms"] += metrics.get("duration_ms") or 0

            if schema is None:
                return result, version, total_metrics

            if isinstance(result, str):
                data = parse_json_object(result)
                validated = schema.model_validate(data)
                return validated, version, total_metrics
            else:
                if isinstance(result, schema):
                    return result, version, total_metrics
                validated = schema.model_validate(result)
                return validated, version, total_metrics

        except Exception as e:
            last_error = str(e)
            logger.warning(f"Self-correction triggered for {agent_name} (attempt {attempt}/{max_retries}): {last_error}")
            pipeline_event(
                f"ai_engine.{agent_name}",
                "self_correction_triggered",
                f"Agent output invalid, retrying ({attempt}/{max_retries})",
                details={"error": last_error}
            )
            if attempt == max_retries:
                raise

    raise RuntimeError(f"Agent {agent_name} failed after {max_retries} attempts")


def run_storyboard_phase(
    *,
    llm: LLMClient,
    model: str,
    temperature: float,
    max_tokens: int,
    project_title: str,
    project_description: str | None,
    extra_brief: str | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """Phase 1: Storyboard generation via Director Agent."""
    return _run_agent_with_self_correction(
        "director",
        run_director,
        schema=None, 
        llm=llm,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        project_title=project_title,
        project_description=project_description,
        extra_brief=extra_brief,
    )


def run_planning_phase(
    *,
    llm: LLMClient,
    model: str,
    temperature: float,
    max_tokens: int,
    storyboard_text: str,
) -> tuple[PlannerOutput, str, dict[str, Any]]:
    """Phase 2: Execution plan generation via Planner Agent."""
    return _run_agent_with_self_correction(
        "planner",
        run_planner,
        schema=PlannerOutput,
        llm=llm,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        storyboard_text=storyboard_text,
    )


def run_single_review_round(
    *,
    llm: LLMClient,
    review_cfg: BuilderReviewLoopConfig,
    code_llm: AgentLLMParams,
    visual_llm: AgentLLMParams,
    manim_code: str,
    sandbox_limits: SandboxLimits,
    preview_video_path: Path | None,
    extract_preview_frame: Callable[[Path, float | None], bytes],
    sync_segments: dict[str, Any] | None = None,
    error_logs: str | None = None,
    runtime_limits: RuntimeLimitsConfig | None = None,
) -> ReviewRoundResponse:
    """Phase 8 — single round: branched logic based on render success/failure."""
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
    
    code_review = empty
    code_passed = True
    visual_review: ReviewResult | None = None
    visual_passed: bool | None = None
    skip_reason: str | None = None

    # 1. Code Review (Always runs if static checks pass, or if there's a render error)
    if error_logs or not syntax_ok or not policy_ok:
        code_review, _pv, cm = run_code_reviewer(
            llm=llm,
            model=code_llm.model,
            temperature=code_llm.temperature,
            max_tokens=code_llm.max_tokens,
            manim_code=manim_code,
            error_logs=error_logs or _err,
            request_timeout_seconds=rt.llm_timeout_seconds("code_reviewer"),
        )
        metrics["code_reviewer"] = cm
        code_passed = False 
        skip_reason = "render_failed_or_static_error"
    else:
        # No render error, no static error -> Logical code review
        code_review, _pv, cm = run_code_reviewer(
            llm=llm,
            model=code_llm.model,
            temperature=code_llm.temperature,
            max_tokens=code_llm.max_tokens,
            manim_code=manim_code,
            error_logs=None,
            request_timeout_seconds=rt.llm_timeout_seconds("code_reviewer"),
        )
        metrics["code_reviewer"] = cm
        code_passed = not _agent_has_blocking(code_review.issues, review_cfg)
    # 2. Visual Review (Parallel if render succeeded)
    # Case B: Render Success -> Run Visual Reviewer regardless of Code Review results
    if not error_logs and syntax_ok and policy_ok:
        if preview_video_path is None or not preview_video_path.is_file():
            skip_reason = "no_preview_video"
            visual_passed = False
        else:
            try:
                # Information Convergence Point: use last segment's end timestamp
                convergence_t = _get_convergence_timestamp(sync_segments)
                frame_jpeg = extract_preview_frame(preview_video_path, convergence_t)
                
                visual_review, _pv2, vm = run_visual_reviewer(
                    llm=llm,
                    model=visual_llm.model,
                    temperature=visual_llm.temperature,
                    max_tokens=visual_llm.max_tokens,
                    frame_jpeg=frame_jpeg,
                    context=(
                        f"Frame is at {convergence_t:.2f}s" if convergence_t else "Frame is at the end of the preview"
                    ),
                    request_timeout_seconds=rt.llm_timeout_seconds("visual_reviewer"),
                )
                metrics["visual_reviewer"] = vm
                visual_passed = _visual_review_passed(cfg=review_cfg, agent_result=visual_review)
                if not visual_passed:
                    if skip_reason:
                         skip_reason += ", visual_review_not_passed"
                    else:
                         skip_reason = "visual_review_not_passed"
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

    early_stop = bool(code_passed and visual_passed is not False)
    if visual_passed is None and not error_logs:
         # This shouldn't happen if logic is correct but for safety:
         early_stop = code_passed

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


def run_builder_loop_phase(
    *,
    scene_id: UUID,
    store: Any,
    job_store: Any,
    llm: LLMClient,
    yaml_data: dict[str, Any],
    runtime_limits: RuntimeLimitsConfig,
    preview_poll_timeout_seconds: float,
    mode: Literal["auto", "hitl"] = "hitl",
    extra_rounds: int | None = None,
) -> tuple[Scene, dict[str, Any]]:
    """Phase 3: The nested Builder-Reviewer loop coordination."""
    scene = store.get_scene(scene_id)
    if scene is None:
        raise ValueError(f"Scene not found: {scene_id}")

    run_id = uuid4()
    t_all = time.perf_counter()
    rounds: list[dict[str, Any]] = []
    review_cfg = load_builder_review_loop(yaml_data)
    builder_llm = resolve_agent_params(yaml_data, "builder")
    code_rev_llm = resolve_agent_params(yaml_data, "code_reviewer")
    visual_rev_llm = resolve_agent_params(yaml_data, "visual_reviewer")
    limits = SandboxLimits(max_bytes=settings.max_manim_code_bytes)
    plan = PlannerOutput.model_validate(scene.planner_output)
    excerpt = scene.storyboard_text[:4000] if scene.storyboard_text else None

    store.update_scene(scene_id, review_loop_status="running")
    chat_history: list[dict[str, str]] = []
    final_status = "failed"
    feedback: str | None = None

    n_rounds = extra_rounds if extra_rounds else max(1, review_cfg.max_rounds)
    try:
        for round_idx in range(1, n_rounds + 1):
            tr = time.perf_counter()
            pipeline_event(
                "builder.review_loop",
                "round_start",
                f"Starting round {round_idx}/{n_rounds}",
                scene_id=str(scene_id),
            )
            # 3a. Builder Agent with Self-Correction for Syntax/Sandbox
            code = ""
            builder_block: dict[str, Any] = {}
            builder_success = False
            
            builder_history = list(chat_history)
            for b_attempt in range(1, 4):
                code, _pv_b, b_met = run_builder(
                    llm=llm,
                    model=builder_llm.model,
                    temperature=builder_llm.temperature,
                    max_tokens=builder_llm.max_tokens,
                    planner=plan,
                    sync_segments=scene.sync_segments,
                    storyboard_excerpt=excerpt,
                    review_feedback=feedback,
                    chat_history=builder_history,
                    request_timeout_seconds=runtime_limits.llm_timeout_seconds("builder"),
                )
                builder_block = {
                    "prompt_version": _pv_b,
                    "duration_ms": b_met.get("duration_ms"),
                    "prompt_tokens": b_met.get("prompt_tokens"),
                    "completion_tokens": b_met.get("completion_tokens"),
                    "attempts": b_attempt,
                }
                
                try:
                    validate_manim_code(code, limits=limits)
                    builder_success = True
                    break
                except SandboxValidationError as exc:
                    err_msg = str(exc)
                    logger.warning(f"Builder self-correction (round {round_idx} attempt {b_attempt}): {err_msg}")
                    builder_history.append({"role": "assistant", "content": code})
                    builder_history.append({"role": "user", "content": f"[SELF-CORRECTION] The code you generated failed validation: {err_msg}. Please fix it."})
            
            if not builder_success:
                rounds.append({
                    "round": round_idx,
                    "error": "builder_failed_after_retries",
                    "builder": builder_block,
                })
                final_status = "failed"
                break
                
            chat_history.append({"role": "assistant", "content": code})

            prev = (scene.manim_code or "").strip()
            stripped = code.strip()
            bumped = stripped != prev
            next_ver = scene.manim_code_version + (1 if bumped else 0)
            scene = store.update_scene(scene_id, manim_code=stripped, manim_code_version=next_ver)
            assert scene is not None

            job_id = uuid4()
            job_store.create_queued_job(
                job_id=job_id,
                project_id=scene.project_id,
                scene_id=scene_id,
                job_type="preview",
                render_quality="720p",
                webhook_url=None,
                docker_image_tag=settings.worker_image_tag,
            )
            pipeline_event(
                "builder.review_loop",
                "preview_job_queued",
                "Builder loop enqueued preview render",
                job_id=str(job_id),
                scene_id=str(scene_id),
                project_id=str(scene.project_id),
            )
            render_manim_scene.apply_async(args=[str(job_id)])

            tw0 = time.perf_counter()
            job = wait_for_render_job(
                job_store,
                job_id,
                timeout_seconds=preview_poll_timeout_seconds,
                poll_interval_seconds=runtime_limits.preview_poll_interval_seconds,
            )
            preview_wait_ms = int((time.perf_counter() - tw0) * 1000)

            mp4 = None
            error_logs = None
            if job.status == "completed":
                u = job.asset_url or ""
                if u.startswith("file://"):
                    p = Path(u.replace("file://", "", 1))
                    if p.is_file():
                        mp4 = p
            else:
                error_logs = job.logs or "Render job failed without logs"
                pipeline_event(
                    "builder.review_loop",
                    "render_failed_triggering_recovery",
                    "Render failed, calling Code Reviewer with logs",
                    job_id=str(job_id),
                    logs_len=len(error_logs),
                )

            # Phase 5: Post-process Sync Validation
            sync_report = None
            if mp4 and scene.duration_seconds:
                # Use ffprobe to get actual video duration
                try:
                    from worker.tts_runtime import _ffprobe_duration_seconds
                    video_dur = _ffprobe_duration_seconds(mp4)
                    sync_report = validate_sync_duration(
                        video_duration=video_dur,
                        audio_duration=scene.duration_seconds
                    )
                    if sync_report["sync_issue"]:
                        logger.warning(f"Sync issue detected: video={video_dur}s, audio={scene.duration_seconds}s")
                        pipeline_event(
                            "builder.review_loop",
                            "sync_issue_detected",
                            "Video and audio durations mismatch",
                            details=sync_report
                        )
                except Exception:
                    logger.exception("Failed to validate sync duration")

            review = run_single_review_round(
                llm=llm,
                review_cfg=review_cfg,
                code_llm=code_rev_llm,
                visual_llm=visual_rev_llm,
                manim_code=stripped,
                sandbox_limits=limits,
                preview_video_path=mp4,
                extract_preview_frame=extract_frame_at_timestamp,
                sync_segments=scene.sync_segments,
                error_logs=error_logs,
                runtime_limits=runtime_limits,
            )

            vr_meta: dict[str, Any] = {}
            if mp4 is not None:
                try:
                    convergence_t = _get_convergence_timestamp(scene.sync_segments)
                    fb = extract_frame_at_timestamp(mp4, convergence_t)
                    h = hashlib.sha256(fb).hexdigest()
                    vr_meta = {"sha256": h, "bytes": len(fb), "timestamp": convergence_t}
                    
                    # Upload to Supabase and log URL for debugging
                    signed_url = upload_preview_frame_and_sign(
                        frame_bytes=fb,
                        project_id=scene.project_id,
                        scene_id=scene_id,
                        round_idx=round_idx,
                    )
                    if signed_url:
                        vr_meta["supabase_url"] = signed_url

                    if len(fb) <= 70_000:
                        vr_meta["jpeg_base64"] = base64.standard_b64encode(fb).decode("ascii")
                except Exception:
                    logger.exception("VR preview frame extract failed")
                    vr_meta["error"] = True

            rounds.append({
                "round": round_idx,
                "wall_ms": int((time.perf_counter() - tr) * 1000),
                "builder": builder_block,
                "preview_job_id": str(job_id),
                "preview_wait_ms": preview_wait_ms,
                "preview_status": job.status,
                "review": review.model_dump(mode="json"),
                "vr_preview": vr_meta,
                "sync_validation": sync_report,
            })

            if review.early_stop:
                final_status = "completed"
                break

            # Phase 6: Consolidated Feedback (Architecture v2)
            feedback_parts = [f"### 📝 Review Feedback (Round {round_idx})\nHệ thống phát hiện các vấn đề cần khắc phục:\n"]
            
            # Code Reviewer Section
            if review.code_review.issues:
                feedback_parts.append("**[Code Reviewer]**")
                for issue in review.code_review.issues[:20]:
                    feedback_parts.append(f"- [{issue.severity}] {issue.code}: {issue.message}")
                    if issue.suggestion:
                        feedback_parts.append(f"- **Suggestion:** `{issue.suggestion}`")
                feedback_parts.append("")

            # Visual Reviewer Section
            if review.visual_review and review.visual_review.issues:
                feedback_parts.append("**[Visual Reviewer]**")
                for issue in review.visual_review.issues[:20]:
                    feedback_parts.append(f"- [{issue.severity}] {issue.code}: {issue.message}")
                    if issue.suggestion:
                        feedback_parts.append(f"- **Suggestion:** `{issue.suggestion}`")
                feedback_parts.append("")

            feedback = "\n".join(feedback_parts).strip()
            if not (review.code_review.issues or (review.visual_review and review.visual_review.issues)):
                feedback = "(no issues found, but early stop was not triggered)"

            # Sliding Window History: Keep only the most recent interaction pair
            # Structure: Assistant (previous code), User (latest feedback)
            chat_history = [
                {"role": "assistant", "content": code},
                {"role": "user", "content": feedback},
            ]
        else:
            if mode == "auto":
                final_status = "failed"
            elif review_cfg.on_max_rounds_exceeded == "hitl_or_fail":
                final_status = "hitl_pending"
            else:
                final_status = "failed"

    except Exception as exc:
        logger.exception("builder_review_loop failed scene_id=%s", scene_id)
        rounds.append({"fatal": str(exc)})
        final_status = "failed"

    total_ms = int((time.perf_counter() - t_all) * 1000)
    
    # Aggregate total token usage
    total_prompt_tokens = 0
    total_completion_tokens = 0
    for r in rounds:
        for agent in ["builder", "review"]:
            if agent in r:
                if agent == "builder":
                    total_prompt_tokens += r[agent].get("prompt_tokens") or 0
                    total_completion_tokens += r[agent].get("completion_tokens") or 0
                else:
                    # review is a dict with code_reviewer and visual_reviewer
                    metrics = r[agent].get("metrics") or {}
                    for m in metrics.values():
                        total_prompt_tokens += m.get("prompt_tokens") or 0
                        total_completion_tokens += m.get("completion_tokens") or 0

    report = {
        "run_id": str(run_id),
        "scene_id": str(scene_id),
        "max_rounds": n_rounds,
        "final_status": final_status,
        "total_duration_ms": total_ms,
        "usage_summary": {
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
        },
        "rounds": rounds,
        "finished_at": datetime.now(tz=UTC).isoformat(),
    }
    insert_pipeline_run_row(
        run_id=run_id,
        project_id=scene.project_id,
        scene_id=scene_id,
        status=final_status,
        report=report,
    )
    out = store.update_scene(scene_id, review_loop_status=final_status)
    assert out is not None
    return out, report
