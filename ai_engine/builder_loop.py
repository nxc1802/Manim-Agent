from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import time
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import UUID, uuid4

from backend.core.config import settings
from backend.services.code_sandbox import SandboxLimits
from backend.services.frame_info import extract_frame_at_timestamp
from backend.services.job_wait import wait_for_render_job
from backend.services.supabase_pipeline_rest import insert_agent_log_row, insert_pipeline_run_row
from backend.services.supabase_storage_rest import upload_preview_frame_and_sign
from backend.services.sync_engine_logic import validate_sync_duration
from pydantic import BaseModel
from shared.code_utils import extract_python_code
from shared.constants import MaxRoundsExceededAction, ReviewLoopMode, SeverityLevel
from shared.pipeline_log import pipeline_event
from shared.schemas.planner_output import PlannerOutput
from shared.schemas.review import ReviewIssue, ReviewResult
from shared.schemas.review_pipeline import AgentLog, ReviewRoundResponse
from shared.schemas.scene import Scene, SceneCodeHistory
from worker.tasks import render_manim_scene

from ai_engine.agents.builder import run_builder
from ai_engine.agents.code_reviewer import run_code_reviewer
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
from ai_engine.prompts import PROMPT_VERSION_VISUAL_REVIEWER
from ai_engine.utils.storage_helper import save_agent_interaction

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="BaseModel")

_SEVERITY_RANK = {
    SeverityLevel.INFO: 0,
    SeverityLevel.WARNING: 1,
    SeverityLevel.ERROR: 2,
    SeverityLevel.BLOCKER: 3,
}


def _severity_at_least(sev: str, minimum: str) -> bool:
    s_val = _SEVERITY_RANK.get(SeverityLevel(sev), 0)
    m_val = _SEVERITY_RANK.get(SeverityLevel(minimum), 1)
    return s_val >= m_val


def _agent_has_blocking(issues: list[ReviewIssue], cfg: BuilderReviewLoopConfig) -> bool:
    for issue in issues:
        if _severity_at_least(issue.severity, cfg.blocking_severity_min):
            return True
        if cfg.stop_when_only_info_severity and issue.severity == SeverityLevel.INFO:
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
            sync = sync_segments  # type: ignore

        if sync.segments:
            return sync.segments[-1].end
    except Exception:
        logger.warning("Failed to parse sync_segments for convergence point")
    return None


def truncate_error_logs(logs: str, max_chars: int = 2000) -> str:
    """Sandwich truncating: keep the beginning and the end of the logs."""
    if not logs or len(logs) <= max_chars:
        return logs

    # Reserve some space for the truncation message
    msg = "\n\n... [TRUNCATED] ...\n\n"
    limit = (max_chars - len(msg)) // 2
    if limit <= 0:
        return logs[-max_chars:]  # Fallback

    return f"{logs[:limit]}{msg}{logs[-limit:]}"


async def _run_agent_with_self_correction(
    agent_name: str, call_fn: Any, schema: type[T] | None, **kwargs: Any
) -> tuple[Any, str, dict[str, Any], str, str]:
    """Helper to call agent and validate schema."""
    try:
        # call_fn is assumed to be async now
        result, version, metrics, system, user = await call_fn(**kwargs)

        if schema is None:
            return result, version, metrics, system, user

        if isinstance(result, str):
            data = parse_json_object(result)
            validated = schema.model_validate(data)
            return validated, version, metrics, system, user
        else:
            if isinstance(result, schema):
                return result, version, metrics, system, user
            validated = schema.model_validate(result)
            return validated, version, metrics, system, user

    except Exception as e:
        logger.error(f"Agent {agent_name} failed: {str(e)}")
        pipeline_event(
            f"ai_engine.{agent_name}",
            "agent_failed",
            "Agent call or validation failed",
            details={"error": str(e)},
        )
        raise


async def run_single_review_round_ex(
    *,
    llm: LLMClient,
    review_cfg: BuilderReviewLoopConfig,
    code_llm: AgentLLMParams,
    visual_llm: AgentLLMParams,
    manim_code: str,
    sandbox_limits: SandboxLimits,
    preview_video_path: str | None,
    extract_preview_frame: Any,
    sync_segments: dict[str, Any] | None = None,
    error_logs: str | None = None,
    use_primitives: bool = True,
    runtime_limits: RuntimeLimitsConfig | None = None,
) -> tuple[ReviewRoundResponse, dict[str, dict[str, str]]]:
    """Phase 8 — single round: branched logic based on render success/failure. Returns (response, prompts)."""
    rt = runtime_limits or RuntimeLimitsConfig(
        worker_man_render_timeout_seconds=3600,
        worker_tts_subprocess_timeout_seconds=900,
        preview_poll_timeout_seconds=900,
        preview_poll_interval_seconds=0.5,
        llm_timeout_default_seconds=600,
        llm_timeouts={},
    )

    empty = ReviewResult(issues=[])
    metrics: dict[str, Any] = {}
    prompts: dict[str, dict[str, str]] = {}

    code_review = empty
    code_passed = True
    visual_review: ReviewResult | None = None
    visual_passed: bool | None = None
    skip_reason: str | None = None

    truncated_logs = truncate_error_logs(error_logs) if error_logs else None

    # 1. Define review tasks
    async def _invoke_code_reviewer():
        return await _run_agent_with_self_correction(
            "code_reviewer",
            run_code_reviewer,
            schema=ReviewResult,
            llm=llm,
            model=code_llm.model,
            temperature=code_llm.temperature,
            max_tokens=code_llm.max_tokens,
            manim_code=manim_code,
            error_logs=truncated_logs,
            use_primitives=use_primitives,
            request_timeout_seconds=rt.llm_timeout_seconds("code_reviewer"),
        )

    async def _invoke_visual_reviewer():
        if not review_cfg.visual_reviewer_enabled:
            return None, "disabled_in_config"
        if not preview_video_path:
            return None, "no_preview_video"

        try:
            convergence_t = _get_convergence_timestamp(sync_segments)
            # frame extraction remains synchronous as it's typically quick file I/O or subprocess
            frame_jpeg = extract_preview_frame(preview_video_path, convergence_t)

            res = await _run_agent_with_self_correction(
                "visual_reviewer",
                run_visual_reviewer,
                schema=ReviewResult,
                llm=llm,
                model=visual_llm.model,
                temperature=visual_llm.temperature,
                max_tokens=visual_llm.max_tokens,
                frame_jpeg=frame_jpeg,
                context=(
                    f"Frame is at {convergence_t:.2f}s"
                    if convergence_t
                    else "Frame is at the end of the preview"
                ),
                request_timeout_seconds=rt.llm_timeout_seconds("visual_reviewer"),
            )
            return res, None
        except Exception:
            logger.exception("Visual review failed")
            err_res = ReviewResult(
                issues=[
                    ReviewIssue(
                        severity=SeverityLevel.ERROR,
                        code="visual_pipeline_error",
                        message="Visual review raised an exception",
                    ),
                ],
            )
            return (err_res, PROMPT_VERSION_VISUAL_REVIEWER, {}, "", ""), "visual_review_error"

    # 2. Execute Reviewers in Parallel
    tasks = [_invoke_code_reviewer()]
    if not error_logs and review_cfg.visual_reviewer_enabled and preview_video_path:
        tasks.append(_invoke_visual_reviewer())

    results = await asyncio.gather(*tasks)

    # Process Code Review result
    code_res = results[0]
    code_review, _pv, cm, csys, cusr = code_res
    metrics["code_reviewer"] = cm
    prompts["code_reviewer"] = {"system": csys, "user": cusr}

    if error_logs:
        code_passed = False
        skip_reason = "render_failed"
    else:
        code_passed = not _agent_has_blocking(code_review.issues, review_cfg)

    # Process Visual Review result if it was run
    if len(results) > 1:
        v_res_data, v_skip = results[1]
        if v_skip:
            if v_res_data:
                visual_review, _pv2, vm, vsys, vusr = v_res_data
                metrics["visual_reviewer"] = vm
                prompts["visual_reviewer"] = {"system": vsys, "user": vusr}
            visual_passed = False if v_skip == "visual_review_error" else None
            skip_reason = v_skip
        else:
            visual_review, _pv2, vm, vsys, vusr = v_res_data
            metrics["visual_reviewer"] = vm
            prompts["visual_reviewer"] = {"system": vsys, "user": vusr}
            visual_passed = _visual_review_passed(cfg=review_cfg, agent_result=visual_review)
            if not visual_passed:
                skip_reason = (
                    skip_reason + ", " if skip_reason else ""
                ) + "visual_review_not_passed"
    elif not error_logs:
        if not review_cfg.visual_reviewer_enabled:
            skip_reason = "disabled_in_config"
        elif not preview_video_path:
            skip_reason = "no_preview_video"
        else:
            skip_reason = "visual_review_not_triggered"

    # 3. Dynamic Early Stop Logic
    pass_results = {
        "code_review_passed": code_passed,
        "visual_review_passed": visual_passed
        if visual_passed is not None
        else (not review_cfg.visual_reviewer_enabled),
    }

    early_stop = True
    for requirement in review_cfg.early_stop_require_all:
        if not pass_results.get(requirement, False):
            early_stop = False
            break

    resp = ReviewRoundResponse(
        static_parse_ok=not error_logs,
        static_imports_ok=not error_logs,
        code_review=code_review,
        code_review_passed=code_passed,
        visual_review=visual_review,
        visual_review_skipped_reason=skip_reason,
        visual_review_passed=visual_passed,
        early_stop=early_stop,
        metrics=metrics,
    )
    return resp, prompts


async def run_single_review_round(
    *,
    llm: LLMClient,
    review_cfg: BuilderReviewLoopConfig,
    code_llm: AgentLLMParams,
    visual_llm: AgentLLMParams,
    manim_code: str,
    sandbox_limits: SandboxLimits,
    preview_video_path: str | None,
    extract_preview_frame: Any,
    sync_segments: dict[str, Any] | None = None,
    error_logs: str | None = None,
    use_primitives: bool = True,
    runtime_limits: RuntimeLimitsConfig | None = None,
) -> ReviewRoundResponse:
    """Convenience wrapper for run_single_review_round_ex."""
    resp, _ = await run_single_review_round_ex(
        llm=llm,
        review_cfg=review_cfg,
        code_llm=code_llm,
        visual_llm=visual_llm,
        manim_code=manim_code,
        sandbox_limits=sandbox_limits,
        preview_video_path=preview_video_path,
        extract_preview_frame=extract_preview_frame,
        sync_segments=sync_segments,
        error_logs=error_logs,
        use_primitives=use_primitives,
        runtime_limits=runtime_limits,
    )
    return resp


async def run_builder_loop_phase(
    *,
    scene_id: UUID,
    store: Any,
    job_store: Any,
    llm: LLMClient,
    yaml_data: dict[str, Any],
    runtime_limits: RuntimeLimitsConfig,
    preview_poll_timeout_seconds: float,
    use_primitives: bool = True,
    mode: ReviewLoopMode = ReviewLoopMode.HITL,
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
    plan = PlannerOutput.model_validate(scene.planner_output)
    excerpt = scene.storyboard_text[:4000] if scene.storyboard_text else None

    # Persistent record in Supabase
    try:
        insert_pipeline_run_row(
            run_id=run_id,
            project_id=scene.project_id,
            scene_id=scene_id,
            status="running",
            report={},
        )
    except Exception:
        logger.exception("Initial pipeline run insertion failed")

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

            # 3a. Builder Agent
            code, _pv_b, b_met, b_sys, b_usr = await run_builder(
                llm=llm,
                model=builder_llm.model,
                temperature=builder_llm.temperature,
                max_tokens=builder_llm.max_tokens,
                planner=plan,
                sync_segments=scene.sync_segments,
                storyboard_excerpt=excerpt,
                use_primitives=use_primitives,
                review_feedback=feedback,
                chat_history=chat_history,
                request_timeout_seconds=runtime_limits.llm_timeout_seconds("builder"),
                is_fix_mode=(round_idx > 1),
            )
            save_agent_interaction(
                scene.project_id, "builder", "generate", b_sys, b_usr, code, round_idx=round_idx
            )

            builder_block = {
                "prompt_version": _pv_b,
                "duration_ms": b_met.get("duration_ms"),
                "prompt_tokens": b_met.get("prompt_tokens"),
                "completion_tokens": b_met.get("completion_tokens"),
                "attempts": 1,
                "prompts": {"system": b_sys, "user": b_usr},
            }

            # Persistent Agent Log to Supabase
            try:
                insert_agent_log_row(
                    AgentLog(
                        run_id=run_id,
                        scene_id=scene_id,
                        round_idx=round_idx,
                        agent_name="builder",
                        attempt=1,
                        prompt_version=_pv_b,
                        system_prompt=b_sys,
                        user_prompt=b_usr,
                        output_text=code,
                        metrics=b_met,
                    )
                )
            except Exception:
                logger.warning("Failed to insert background agent log to Supabase")

            chat_history.append({"role": "assistant", "content": code})

            prev = (scene.manim_code or "").strip()
            stripped = extract_python_code(code).strip()
            bumped = stripped != prev
            next_ver = scene.manim_code_version + (1 if bumped else 0)
            scene = store.update_scene(scene_id, manim_code=stripped, manim_code_version=next_ver)
            assert scene is not None

            # Save snapshot to history
            try:
                store.save_scene_code_history(
                    SceneCodeHistory(
                        scene_id=scene_id,
                        run_id=run_id,
                        version=next_ver,
                        round_idx=round_idx,
                        manim_code=stripped,
                    )
                )
            except Exception:
                logger.exception("Failed to save scene_code_history")

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
            render_manim_scene.apply_async(args=[str(job_id)], queue="render")

            tw0 = time.perf_counter()
            # wait_for_render_job is likely blocking, we can keep it for now or wrap in to_thread
            job = await asyncio.to_thread(
                wait_for_render_job,
                job_store,
                job_id,
                timeout_seconds=preview_poll_timeout_seconds,
                poll_interval_seconds=runtime_limits.preview_poll_interval_seconds,
            )
            preview_wait_ms = int((time.perf_counter() - tw0) * 1000)

            mp4_url = None
            error_logs = None
            if job.status == "completed":
                mp4_url = job.asset_url
            else:
                error_logs = job.logs or "Render job failed without logs"

            # Sync Validation
            sync_report = None
            if mp4_url and scene.duration_seconds:
                try:
                    video_dur = job.metadata.get("video_duration")
                    if video_dur is None:
                        # Fallback to sync ffprobe if needed
                        from worker.tts_runtime import _ffprobe_duration_seconds

                        video_dur = _ffprobe_duration_seconds(mp4_url)

                    sync_report = validate_sync_duration(
                        video_duration=video_dur, audio_duration=scene.duration_seconds
                    )
                except Exception:
                    logger.exception("Failed to validate sync duration")

            review, r_prompts = await run_single_review_round_ex(
                llm=llm,
                review_cfg=review_cfg,
                code_llm=code_rev_llm,
                visual_llm=visual_rev_llm,
                manim_code=stripped,
                sandbox_limits=SandboxLimits(max_bytes=settings.max_manim_code_bytes),
                preview_video_path=mp4_url,
                extract_preview_frame=extract_frame_at_timestamp,
                sync_segments=scene.sync_segments,
                error_logs=error_logs,
                use_primitives=use_primitives,
                runtime_limits=runtime_limits,
            )

            # Persistent Agent Logs for Reviewers
            for agent_name, p in r_prompts.items():
                try:
                    output_txt = None
                    met = review.metrics.get(agent_name) or {}
                    if agent_name == "code_reviewer":
                        output_txt = review.code_review.model_dump_json()
                    elif agent_name == "visual_reviewer" and review.visual_review:
                        output_txt = review.visual_review.model_dump_json()

                    insert_agent_log_row(
                        AgentLog(
                            run_id=run_id,
                            scene_id=scene_id,
                            round_idx=round_idx,
                            agent_name=agent_name,
                            system_prompt=p.get("system"),
                            user_prompt=p.get("user"),
                            output_text=output_txt,
                            metrics=met,
                        )
                    )
                    save_agent_interaction(
                        scene.project_id,
                        agent_name,
                        "review",
                        p.get("system"),
                        p.get("user"),
                        output_txt,
                        round_idx=round_idx,
                    )
                except Exception:
                    logger.exception(f"Failed to insert {agent_name} agent_log")

            vr_meta: dict[str, Any] = {}
            if mp4_url is not None:
                try:
                    convergence_t = _get_convergence_timestamp(scene.sync_segments)
                    fb = extract_frame_at_timestamp(mp4_url, convergence_t)
                    h = hashlib.sha256(fb).hexdigest()
                    vr_meta = {"sha256": h, "bytes": len(fb), "timestamp": convergence_t}

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

            rounds.append(
                {
                    "round": round_idx,
                    "wall_ms": int((time.perf_counter() - tr) * 1000),
                    "builder": builder_block,
                    "preview_job_id": str(job_id),
                    "preview_wait_ms": preview_wait_ms,
                    "preview_status": job.status,
                    "review": review.model_dump(mode="json"),
                    "review_prompts": r_prompts,
                    "vr_preview": vr_meta,
                    "sync_validation": sync_report,
                }
            )

            if review.early_stop:
                final_status = "completed"
                break

            # Phase 6: Consolidated Feedback
            feedback_parts = [f"### 📝 Review Feedback (Round {round_idx})\n"]
            if review.code_review.issues:
                feedback_parts.append("**[Code Reviewer]**")
                for issue in review.code_review.issues[:20]:
                    feedback_parts.append(f"- [{issue.severity}] {issue.code}: {issue.message}")
                    if issue.suggestion:
                        feedback_parts.append(f"- **Suggestion:** `{issue.suggestion}`")
            if review.visual_review and review.visual_review.issues:
                feedback_parts.append("\n**[Visual Reviewer]**")
                for issue in review.visual_review.issues[:20]:
                    feedback_parts.append(f"- [{issue.severity}] {issue.code}: {issue.message}")
                    if issue.suggestion:
                        feedback_parts.append(f"- **Suggestion:** `{issue.suggestion}`")

            feedback = "\n".join(feedback_parts).strip()
            chat_history = [
                {"role": "assistant", "content": code},
                {"role": "user", "content": truncate_error_logs(feedback, max_chars=4000)},
            ]
        else:
            if mode == ReviewLoopMode.AUTO:
                final_status = "failed"
            elif review_cfg.on_max_rounds_exceeded == MaxRoundsExceededAction.HITL_OR_FAIL:
                final_status = "hitl_pending"
            else:
                final_status = "failed"

    except Exception as exc:
        logger.exception("builder_review_loop failed scene_id=%s", scene_id)
        rounds.append({"fatal": str(exc)})
        final_status = "failed"

    total_ms = int((time.perf_counter() - t_all) * 1000)
    report = {
        "run_id": str(run_id),
        "scene_id": str(scene_id),
        "max_rounds": n_rounds,
        "final_status": final_status,
        "total_duration_ms": total_ms,
        "rounds": rounds,
        "finished_at": datetime.now(tz=UTC).isoformat(),
    }
    try:
        insert_pipeline_run_row(
            run_id=run_id,
            project_id=scene.project_id,
            scene_id=scene_id,
            status=final_status,
            report=report,
        )
    except Exception:
        logger.exception("Final pipeline run update failed")

    out = store.update_scene(scene_id, review_loop_status=final_status)
    return out, report
