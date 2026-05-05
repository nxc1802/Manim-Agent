import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import NamedTuple
from uuid import UUID

from backend.core.config import settings
from backend.db.content_store import get_content_store
from backend.services.job_store import RedisRenderJobStore
from backend.services.redis_client import get_redis
from shared.pipeline_log import (
    get_pipeline_trace_id,
    pipeline_debug,
    pipeline_error,
    pipeline_event,
)
from shared.schemas.render_job import RenderJobType, RenderQuality

logger = logging.getLogger(__name__)


class RenderManimResult(NamedTuple):
    video_path: Path
    job_dir: Path
    stdout_tail: str
    stderr_tail: str
    command: list[str]
    silent_video_path: Path | None = None
    audio_path: Path | None = None


def manim_quality_flags(*, job_type: RenderJobType, quality: RenderQuality) -> list[str]:
    if job_type == "preview":
        return ["-qh"]
    if quality == "4k":
        return ["-qk"]
    if quality == "1080p":
        return ["-qh"]
    return ["-qh"]  # Default to high for non-preview if not specified


def render_manim_scene_to_disk(
    *,
    job_id: UUID,
    job_type: RenderJobType,
    quality: RenderQuality,
    timeout: int = 1200,
) -> RenderManimResult:
    """Run `manim render` into an isolated per-job output directory."""
    repo_root = Path(settings.repo_root).resolve()
    # Create a temporary directory for this job to ensure no local leakage
    job_dir = Path(tempfile.mkdtemp(prefix=f"manim_job_{job_id}_")).resolve()
    media_dir = job_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    job_store = RedisRenderJobStore(get_redis())
    job = job_store.get(job_id)
    if job is None:
        msg = f"Render job not found: {job_id}"
        raise RuntimeError(msg)

    scene = None
    if job.scene_id is not None:
        content = get_content_store()
        scene = content.get_scene(job.scene_id)
        if scene is None:
            msg = f"Scene {job.scene_id} not found in content store for job {job_id}"
            logger.error(msg)
            raise RuntimeError(msg)

        mcode = (scene.manim_code or "").strip()
        logger.info(
            "Retrieved scene_id=%s manim_code_len=%d version=%d",
            job.scene_id,
            len(mcode),
            scene.manim_code_version,
        )

        if not mcode:
            msg = f"Scene {job.scene_id} missing manim_code for render (job_id={job_id})"
            logger.error(msg)
            raise RuntimeError(msg)

        # Inject metadata: durations for Dynamic Template
        durations_json = json.dumps(scene.sync_segments or {}, ensure_ascii=False)
        metadata_injection = f"\n# Dynamic Template Metadata\nBEAT_DURATIONS = {durations_json}\n\n"

        scene_file = (job_dir / "generated_scene.py").resolve()
        # Ensure __future__ imports are at the very top
        # (SyntaxError if BEAT_DURATIONS is before them)
        lines = mcode.splitlines(keepends=True)
        future_lines = []
        other_lines = []
        for line in lines:
            if "__future__" in line and ("import" in line or "from" in line):
                future_lines.append(line)
            else:
                other_lines.append(line)

        full_code = "".join(future_lines) + metadata_injection + "".join(other_lines)
        scene_file.write_text(full_code, encoding="utf-8")
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
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        pipeline_error(
            "worker.manim",
            "subprocess_timeout",
            "manim render timed out",
            trace_id=tid,
            job_id=str(job_id),
            details={"timeout_seconds": timeout},
        )
        raise RuntimeError(f"Manim render timed out after {timeout} seconds") from exc
    except subprocess.CalledProcessError as exc:
        stdout_tail = (exc.stdout or "")[-8000:]
        stderr_tail = (exc.stderr or "")[-8000:]
        pipeline_error(
            "worker.manim",
            "subprocess_failed",
            "manim exited non-zero",
            trace_id=tid,
            job_id=str(job_id),
            details={
                "returncode": exc.returncode,
                "stderr_tail": (stderr_tail or "")[:1500],
            },
        )
        detail = (stderr_tail or stdout_tail or "").strip() or f"manim exit code {exc.returncode}"
        raise RuntimeError(detail) from exc

    stdout_tail = (proc.stdout or "")[-8000:]
    stderr_tail = (proc.stderr or "")[-8000:]

    matches = sorted(media_dir.rglob(f"{scene_class}.mp4"))
    if not matches:
        msg = f"No mp4 produced under {media_dir}"
        raise FileNotFoundError(msg)

    video_path = matches[-1]
    pipeline_event(
        "worker.manim",
        "subprocess_ok",
        "mp4 produced",
        trace_id=tid,
        job_id=str(job_id),
        details={"mp4": str(video_path)},
    )

    silent_video = matches[-1]
    local_audio_path = None

    # --- Audio Merging Logic ---
    if scene and scene.audio_url:
        try:
            logger.info("Merging audio for scene: %s, URL: %s", job_id, scene.audio_url)
            pipeline_event(
                "worker.manim",
                "audio_merge_start",
                "Downloading and merging audio",
                job_id=str(job_id),
                details={"audio_url": scene.audio_url},
            )

            audio_ext = "mp3"
            if ".wav" in scene.audio_url.lower():
                audio_ext = "wav"
            local_audio = job_dir / f"voice.{audio_ext}"

            import httpx

            full_audio_url = scene.audio_url
            if not full_audio_url.startswith("http"):
                base_url = (settings.supabase_url or "").strip()
                if base_url and not base_url.endswith("/storage/v1"):
                    base_url = f"{base_url}/storage/v1"
                full_audio_url = f"{base_url}{scene.audio_url}"

            logger.info("Downloading audio from: %s", full_audio_url)
            pipeline_event(
                "worker.manim",
                "audio_download_start",
                "Downloading audio from resolved URL",
                details={"url": full_audio_url},
            )

            with httpx.stream("GET", full_audio_url, follow_redirects=True) as r:
                r.raise_for_status()
                with open(local_audio, "wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)

            local_audio_path = local_audio
            logger.info(
                "Audio downloaded to: %s (Size: %s bytes)", local_audio, local_audio.stat().st_size
            )

            merged_video = job_dir / f"{scene_class}_merged.mp4"
            merge_cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(local_audio),
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                str(merged_video),
            ]

            logger.info("Running merge command: %s", " ".join(merge_cmd))
            merge_proc = subprocess.run(merge_cmd, check=True, capture_output=True, text=True)
            logger.info("FFmpeg merge stdout: %s", merge_proc.stdout)
            logger.info("FFmpeg merge stderr: %s", merge_proc.stderr)

            if merged_video.exists():
                video_path = merged_video
                logger.info("Audio merged successfully. New video_path: %s", video_path)
                pipeline_event(
                    "worker.manim",
                    "audio_merge_ok",
                    "Audio merged successfully",
                    job_id=str(job_id),
                )
        except Exception as e:
            logger.exception("Failed to merge audio: %s", e)
            pipeline_error("worker.manim", "audio_merge_failed", str(e), job_id=str(job_id))

    return RenderManimResult(
        video_path=video_path,
        job_dir=job_dir,
        stdout_tail=stdout_tail,
        stderr_tail=stderr_tail,
        command=cmd,
        silent_video_path=silent_video,
        audio_path=local_audio_path,
    )
