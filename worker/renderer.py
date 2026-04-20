from __future__ import annotations

import subprocess
from pathlib import Path
from typing import NamedTuple
from uuid import UUID

from backend.core.config import settings
from backend.services.content_store import RedisContentStore
from backend.services.job_store import RedisRenderJobStore
from backend.services.redis_client import get_redis
from shared.pipeline_log import get_pipeline_trace_id, pipeline_debug, pipeline_event
from shared.schemas.render_job import RenderJobType, RenderQuality


class RenderManimResult(NamedTuple):
    video_path: Path
    stdout_tail: str
    stderr_tail: str
    command: list[str]


def manim_quality_flags(*, job_type: RenderJobType, quality: RenderQuality) -> list[str]:
    if job_type == "preview":
        return ["-ql"]
    if quality == "4k":
        return ["-qk"]
    if quality == "1080p":
        return ["-qh"]
    return ["-qm"]


def render_manim_scene_to_disk(
    *,
    job_id: UUID,
    job_type: RenderJobType,
    quality: RenderQuality,
) -> RenderManimResult:
    """Run `manim render` into an isolated per-job output directory."""
    repo_root = Path(settings.repo_root).resolve()
    job_dir = (repo_root / settings.output_dir / "jobs" / str(job_id)).resolve()
    job_dir.mkdir(parents=True, exist_ok=True)
    media_dir = job_dir / "media"

    job_store = RedisRenderJobStore(get_redis())
    job = job_store.get(job_id)
    if job is None:
        msg = f"Render job not found: {job_id}"
        raise RuntimeError(msg)

    if job.scene_id is not None:
        content = RedisContentStore(get_redis())
        scene = content.get_scene(job.scene_id)
        if scene is None or not (scene.manim_code and scene.manim_code.strip()):
            msg = f"Scene {job.scene_id} missing manim_code for render"
            raise RuntimeError(msg)
        scene_file = (job_dir / "generated_scene.py").resolve()
        scene_file.write_text(scene.manim_code, encoding="utf-8")
        scene_class = settings.generated_scene_class
    else:
        scene_file = (repo_root / settings.manim_scene_file).resolve()
        if not scene_file.is_file():
            msg = f"Scene file not found: {scene_file}"
            raise FileNotFoundError(msg)
        scene_class = settings.manim_scene_class

    q_flags = manim_quality_flags(job_type=job_type, quality=quality)
    cmd = [
        "manim",
        "render",
        *q_flags,
        str(scene_file),
        scene_class,
        "--media_dir",
        str(media_dir),
    ]

    tid = get_pipeline_trace_id()
    pipeline_event(
        "worker.manim",
        "subprocess_start",
        "Running manim render",
        trace_id=tid,
        job_id=str(job_id),
        details={"scene_class": scene_class, "flags": q_flags, "scene_file": str(scene_file)},
    )
    pipeline_debug(
        "worker.manim",
        "subprocess_cmd",
        "Full manim command",
        trace_id=tid,
        job_id=str(job_id),
        details={"argv": cmd},
    )
    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        check=False,
        capture_output=True,
        text=True,
    )
    stdout_tail = (proc.stdout or "")[-8000:]
    stderr_tail = (proc.stderr or "")[-8000:]
    if proc.returncode != 0:
        pipeline_event(
            "worker.manim",
            "subprocess_failed",
            "manim exited non-zero",
            trace_id=tid,
            job_id=str(job_id),
            details={
                "returncode": proc.returncode,
                "stderr_tail": (stderr_tail or "")[:1500],
            },
        )
        detail = (stderr_tail or stdout_tail or "").strip() or f"manim exit code {proc.returncode}"
        raise RuntimeError(detail)

    matches = sorted(media_dir.rglob(f"{scene_class}.mp4"))
    if not matches:
        msg = f"No mp4 produced under {media_dir}"
        raise FileNotFoundError(msg)
    pipeline_event(
        "worker.manim",
        "subprocess_ok",
        "mp4 produced",
        trace_id=tid,
        job_id=str(job_id),
        details={"mp4": str(matches[-1])},
    )
    return RenderManimResult(matches[-1], stdout_tail, stderr_tail, cmd)
