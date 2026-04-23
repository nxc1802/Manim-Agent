from __future__ import annotations

import base64
import hashlib
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from ai_engine.agents.builder import run_builder
from ai_engine.config import RuntimeLimitsConfig, load_builder_review_loop, resolve_agent_params
from ai_engine.llm_client import LLMClient
from ai_engine.orchestrator import run_single_review_round
from shared.pipeline_log import pipeline_event
from shared.schemas.planner_output import PlannerOutput
from shared.schemas.review import ReviewResult
from shared.schemas.scene import Scene
from worker.tasks import render_manim_scene

from backend.core.config import settings
from backend.services.code_sandbox import SandboxLimits, SandboxValidationError, validate_manim_code
from backend.services.content_store import get_content_store
from backend.services.frame_info import extract_end_of_play_jpeg_frame
from backend.services.job_store import RedisRenderJobStore
from backend.services.job_wait import wait_for_render_job
from backend.services.supabase_pipeline_rest import insert_pipeline_run_row


def revert_to_checkpoint(scene_id: UUID, store: Any) -> Scene:
    """Unlock checkpoint: reset review_loop to idle, unblock plan/voice for edits."""
    updated = store.update_scene(
        scene_id,
        review_loop_status="idle",
        plan_status="pending_review",
        voice_script_status="pending_review",
        manim_code_version=1,
    )
    if updated is None:
        msg = f"Failed to revert scene: {scene_id}"
        raise ValueError(msg)
    return updated

logger = logging.getLogger(__name__)


def _local_mp4_from_job(asset_url: str | None) -> Path | None:
    u = asset_url or ""
    if not u.startswith("file://"):
        return None
    p = Path(u.replace("file://", "", 1))
    return p if p.is_file() else None


def _issues_text(res: ReviewResult) -> str:
    lines = [f"[{i.severity}] {i.code}: {i.message}" for i in res.issues[:80]]
    return "\n".join(lines) if lines else "(no issues)"


def run_builder_review_loop(
    *,
    scene_id: UUID,
    store: Any,
    job_store: RedisRenderJobStore,
    llm: LLMClient,
    yaml_data: dict[str, Any],
    runtime_limits: RuntimeLimitsConfig,
    preview_poll_timeout_seconds: float,
    mode: Literal["auto", "hitl"] = "hitl",
    extra_rounds: int | None = None,
) -> tuple[Scene, dict[str, Any]]:
    """Run Builder → preview render → Code + Visual review for up to ``max_rounds`` rounds."""
    scene = store.get_scene(scene_id)
    if scene is None:
        msg = f"Scene not found: {scene_id}"
        raise ValueError(msg)

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

    updated = store.update_scene(scene_id, review_loop_status="running")
    assert updated is not None
    scene = updated
    chat_history: list[dict[str, str]] = []
    final_status = "failed"
    feedback: str | None = None

    # Handle extra_rounds if we are continuing a previous run
    n_rounds = extra_rounds if extra_rounds else max(1, review_cfg.max_rounds)
    try:
        for round_idx in range(1, n_rounds + 1):
            tr = time.perf_counter()
            pipeline_event(
                "builder.review_loop",
                "round_start",
                f"Starting round {round_idx}/{n_rounds}",
                scene_id=scene_id,
            )
            code, _pv_b, b_met = run_builder(
                llm=llm,
                model=builder_llm.model,
                temperature=builder_llm.temperature,
                max_tokens=builder_llm.max_tokens,
                planner=plan,
                sync_segments=scene.sync_segments,
                storyboard_excerpt=excerpt,
                review_feedback=feedback,
                chat_history=chat_history,
                request_timeout_seconds=runtime_limits.llm_timeout_seconds("builder"),
            )
            chat_history.append({"role": "assistant", "content": code})
            builder_block: dict[str, Any] = {
                "prompt_version": _pv_b,
                "duration_ms": b_met.get("duration_ms"),
                "prompt_tokens": b_met.get("prompt_tokens"),
                "completion_tokens": b_met.get("completion_tokens"),
            }

            try:
                validate_manim_code(code, limits=limits)
            except SandboxValidationError as exc:
                rounds.append(
                    {
                        "round": round_idx,
                        "error": "sandbox_validation",
                        "detail": str(exc),
                        "builder": builder_block,
                    },
                )
                final_status = "failed"
                break

            prev = (scene.manim_code or "").strip()
            stripped = code.strip()
            bumped = stripped != prev
            next_ver = scene.manim_code_version + (1 if bumped else 0)
            scene_u = store.update_scene(scene_id, manim_code=stripped, manim_code_version=next_ver)
            assert scene_u is not None
            scene = scene_u

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

            # BRANCHING LOGIC: Success vs Failure
            mp4 = None
            error_logs = None
            if job.status == "completed":
                mp4 = _local_mp4_from_job(job.asset_url)
            else:
                # Get last logs from job store - usually contains the stderr of manim crash
                error_logs = job.logs or "Render job failed without logs"
                pipeline_event(
                    "builder.review_loop",
                    "render_failed_triggering_recovery",
                    "Render failed, calling Code Reviewer with logs",
                    job_id=str(job_id),
                    logs_len=len(error_logs),
                )

            review = run_single_review_round(
                llm=llm,
                review_cfg=review_cfg,
                code_llm=code_rev_llm,
                visual_llm=visual_rev_llm,
                manim_code=stripped,
                sandbox_limits=limits,
                preview_video_path=mp4,
                extract_preview_frame=extract_end_of_play_jpeg_frame,
                error_logs=error_logs,
                runtime_limits=runtime_limits,
            )

            vr_meta: dict[str, Any] = {}
            if mp4 is not None and mp4.is_file():
                try:
                    fb = extract_end_of_play_jpeg_frame(mp4)
                    h = hashlib.sha256(fb).hexdigest()
                    vr_meta = {"sha256": h, "bytes": len(fb)}
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
                    "vr_preview": vr_meta,
                },
            )

            if review.early_stop:
                final_status = "completed"
                break

            # Feedback synthesis for next round
            fb_parts = []
            if not review.code_review_passed:
                fb_parts.extend(["### code_reviewer (Critical Fix Needed)", _issues_text(review.code_review)])
            
            if review.visual_review is not None:
                fb_parts.extend(["### visual_reviewer", _issues_text(review.visual_review)])
            
            feedback = "\n".join(fb_parts)
            # Update history with Reviewer's feedback for next round
            chat_history.append({"role": "user", "content": f"Feedback for previous version: {feedback}"})
        else:
            if mode == "auto":
                final_status = "failed"
            elif review_cfg.on_max_rounds_exceeded == "hitl_or_fail":
                final_status = "hitl_pending"
            else:
                final_status = "failed"

    except Exception as exc:  # noqa: BLE001
        logger.exception("builder_review_loop failed scene_id=%s", scene_id)
        rounds.append({"fatal": str(exc)})
        final_status = "failed"

    total_ms = int((time.perf_counter() - t_all) * 1000)
    report: dict[str, Any] = {
        "run_id": str(run_id),
        "scene_id": str(scene_id),
        "max_rounds": n_rounds,
        "final_status": final_status,
        "total_duration_ms": total_ms,
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
