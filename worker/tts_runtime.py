from __future__ import annotations

import json
import logging
import shutil
import struct
import subprocess
import tempfile
import wave
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from ai_engine.piper_config import PiperRuntimeConfig, load_piper_runtime_config
from backend.core.config import settings
from backend.db.content_store import get_content_store
from backend.services.redis_client import get_redis
from backend.services.supabase_pipeline_rest import insert_worker_service_audit_row
from backend.services.supabase_voice_rest import patch_scene_audio_row, patch_voice_job_row
from backend.services.sync_engine_logic import align_beats_to_audio
from backend.services.tts.segment_alignment import segment_time_alignment
from backend.services.voice_job_store import RedisVoiceJobStore
from shared.pipeline_log import (
    get_pipeline_trace_id,
    pipeline_error,
    pipeline_event,
)
from shared.schemas.planner_output import PlannerOutput
from shared.schemas.voice_segments import SegmentSpan, VoiceSegmentTimestamps

from worker.supabase_storage import upload_voice_artifact_if_configured

logger = logging.getLogger(__name__)


def _ffprobe_duration_seconds(path: str | Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return max(float(proc.stdout.strip()), 0.05)


def _audio_duration_seconds(path: str | Path) -> float:
    """Prefer ffprobe; fall back to WAV header when ffprobe is unavailable (e.g. CI slim images)."""
    try:
        return _ffprobe_duration_seconds(path)
    except Exception:
        try:
            with wave.open(str(path), "r") as wf:
                return max(wf.getnframes() / float(wf.getframerate()), 0.05)
        except Exception:
            logger.exception("Could not read audio duration for %s", path)
            return 1.0


def _write_silent_wav(path: Path, duration_seconds: float) -> None:
    nchannels, sampwidth, framerate = 1, 2, 22050
    nframes = max(int(framerate * duration_seconds), 1)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(nchannels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)
        silence = struct.pack("<h", 0)
        wf.writeframes(silence * nframes)


def _run_piper(cfg: PiperRuntimeConfig, text: str, out_wav: Path) -> list[dict[str, Any]]:
    model = Path(cfg.voice_model_path)
    cmd = [
        cfg.binary,
        "--model",
        str(model),
        "--output_file",
        str(out_wav),
        "--length_scale",
        str(cfg.length_scale),
        "--noise_scale",
        str(cfg.noise_scale),
        "--sentence_silence",
        str(cfg.sentence_silence),
        "--output-json",
    ]
    proc = subprocess.run(
        cmd,
        input=text.encode("utf-8"),
        capture_output=True,
        check=True,
        timeout=900,
    )
    metadata = []
    for line in proc.stdout.decode("utf-8").splitlines():
        if line.strip():
            try:
                metadata.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return metadata


def _concat_wavs(paths: list[Path], out_wav: Path) -> None:
    if not paths:
        return
    if len(paths) == 1:
        shutil.copy(paths[0], out_wav)
        return

    # Use ffmpeg concat filter to combine WAVs
    filter_complex = "".join([f"[{i}:a]" for i in range(len(paths))])
    filter_complex += f"concat=n={len(paths)}:v=0:a=1[a]"
    cmd = ["ffmpeg", "-y"]
    for p in paths:
        cmd.extend(["-i", str(p)])
    cmd.extend(["-filter_complex", filter_complex, "-map", "[a]", str(out_wav)])
    subprocess.run(cmd, check=True, capture_output=True)


def execute_voice_job(job_id: UUID) -> None:
    tid = get_pipeline_trace_id()
    vstore = RedisVoiceJobStore(get_redis())
    cstore = get_content_store()
    job = vstore.get(job_id)
    if job is None:
        logger.error("voice job missing: %s", job_id)
        pipeline_error(
            "worker.tts",
            "job_missing",
            "Voice job not found in Redis",
            voice_job_id=str(job_id),
            trace_id=tid,
        )
        return

    vstore.update(
        job_id,
        status="synthesizing",
        started_at=datetime.now(tz=UTC),
        progress=10,
        logs="Starting TTS (Piper)...",
    )
    job = vstore.get(job_id)
    if job is None:
        logger.error("voice job disappeared after update: %s", job_id)
        return
    patch_voice_job_row(job)

    scene = cstore.get_scene(job.scene_id)
    planner_output = None
    if scene and scene.planner_output:
        try:
            planner_output = PlannerOutput.model_validate(scene.planner_output)
        except Exception:
            logger.warning("Failed to parse planner_output for scene_id=%s", job.scene_id)

    text_raw = job.metadata.get("synthesis_text")
    text = text_raw.strip() if isinstance(text_raw, str) else ""
    if not text:
        _fail(vstore, job_id, "synthesis_text_missing", "Missing synthesis_text in job metadata")
        pipeline_error(
            "worker.tts",
            "validation_failed",
            "Missing synthesis_text",
            voice_job_id=str(job_id),
            trace_id=tid,
        )
        return

    pipeline_event(
        "worker.tts",
        "job_loaded",
        "Starting Piper synthesis",
        voice_job_id=str(job_id),
        trace_id=tid,
        project_id=str(job.project_id),
        scene_id=str(job.scene_id),
        details={"text_chars": len(text), "voice_engine": job.voice_engine, "has_planner": bool(planner_output)},
    )

    piper_cfg = load_piper_runtime_config()
    with tempfile.TemporaryDirectory(prefix="tts_") as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        out_wav = tmpdir / "speech.wav"
        
        try:
            model = Path(piper_cfg.voice_model_path)
            bin_path = Path(piper_cfg.binary)
            bin_ok = bin_path.is_file() if bin_path.is_absolute() else shutil.which(piper_cfg.binary)
            
            spans: list[SegmentSpan] = []
            beat_durations: dict[str, float] = {}

            if not bin_ok or not model.is_file():
                logger.warning("Piper binary or model missing; falling back to silent mock for local testing.")
                if planner_output:
                    t = 0.0
                    for beat in planner_output.beats:
                        b_txt = beat.narration_hint.strip()
                        if not b_txt:
                            continue
                        dur = max(len(b_txt) / 15.0, 0.5)
                        beat_durations[beat.step_label] = dur
                        spans.append(SegmentSpan(text=b_txt, start=t, end=t + dur))
                        t += dur
                    duration_f = t
                    _write_silent_wav(out_wav, duration_f)
                else:
                    duration_f = max(len(text) / 15.0, 1.0)
                    _write_silent_wav(out_wav, duration_f)
                logs = f"Mock TTS synthesis completed (duration={duration_f:.1f}s)."
            else:
                if planner_output:
                    beat_wavs: list[Path] = []
                    t = 0.0
                    for i, beat in enumerate(planner_output.beats):
                        b_txt = beat.narration_hint.strip()
                        if not b_txt:
                            continue
                        b_wav = tmpdir / f"beat_{i}.wav"
                        _run_piper(piper_cfg, b_txt, b_wav)
                        dur = _audio_duration_seconds(b_wav)
                        spans.append(SegmentSpan(text=b_txt, start=t, end=t + dur))
                        t += dur
                        beat_wavs.append(b_wav)
                    
                    _concat_wavs(beat_wavs, out_wav)
                    duration_f = _audio_duration_seconds(out_wav)
                    
                    # Use deterministic sync logic to ensure consistency
                    ts = VoiceSegmentTimestamps(segments=spans)
                    beat_durations = align_beats_to_audio(planner_output, ts)
                    
                    logs = "Piper beat-based synthesis completed."
                else:
                    meta_json = _run_piper(piper_cfg, text, out_wav)
                    logs = "Piper full-text synthesis completed."
                    duration_f = _audio_duration_seconds(out_wav)
                    
                    # Extract precise timestamps from Piper JSON metadata
                    # Piper JSON has "audio_duration" in seconds for each sentence
                    t = 0.0
                    for item in meta_json:
                        s_txt = item.get("text", "")
                        s_dur = float(item.get("audio_duration", 0.0))
                        if s_dur > 0:
                            spans.append(SegmentSpan(text=s_txt, start=t, end=t + s_dur))
                            t += s_dur

            pipeline_event(
                "worker.tts",
                "piper_done",
                "WAV generated (mock or real)",
                voice_job_id=str(job_id),
                trace_id=tid,
            )
            
            if spans:
                ts = VoiceSegmentTimestamps(segments=spans)
            else:
                # Fallback for unexpected cases
                ts = segment_time_alignment(text, total_duration_seconds=duration_f)
                
            VoiceSegmentTimestamps.model_validate(ts.model_dump())

            remote_url = upload_voice_artifact_if_configured(
                wav_path=out_wav,
                project_id=job.project_id,
                job_id=job_id,
            )
            asset_url = remote_url if remote_url else f"file://{out_wav}"
            pipeline_event(
                "worker.tts",
                "artifact_ready",
                "Voice WAV uploaded or local URI",
                voice_job_id=str(job_id),
                trace_id=tid,
                details={"has_remote_url": bool(remote_url), "duration_seconds": duration_f},
            )

            meta: dict[str, Any] = {
                **job.metadata,
                "timestamps": ts.model_dump(mode="json"),
                "beat_durations": beat_durations,
                "audio_format": "wav",
                "granularity": "segment",
                "duration_seconds": duration_f,
            }
            vstore.update(
                job_id,
                status="completed",
                progress=100,
                asset_url=asset_url,
                logs=logs,
                metadata=meta,
                completed_at=datetime.now(tz=UTC),
            )
            job_done = vstore.get(job_id)
            if job_done is not None:
                patch_voice_job_row(job_done)

            ts_payload: dict[str, Any] = ts.model_dump(mode="json")
            scene_updates: dict[str, object] = {
                "audio_url": asset_url,
                "timestamps": ts_payload,
                "duration_seconds": float(round(duration_f, 3)),
            }
            # Store beat_durations in scene for Manim Worker to consume
            if beat_durations:
                scene_updates["sync_segments"] = beat_durations

            override = job.metadata.get("voice_script_override")
            if isinstance(override, str) and override.strip():
                scene_updates["voice_script"] = override.strip()
                
            updated = cstore.update_scene(job.scene_id, **scene_updates)
            if updated is None:
                logger.error("scene missing for voice job scene_id=%s", job.scene_id)
            else:
                vs = scene_updates.get("voice_script")
                patch_scene_audio_row(
                    scene_id=job.scene_id,
                    audio_url=asset_url,
                    timestamps=ts_payload,
                    duration_seconds=float(round(duration_f, 3)),
                    voice_script=vs if isinstance(vs, str) else None,
                    update_voice_script="voice_script" in scene_updates,
                )
            
            insert_worker_service_audit_row(
                audit_id=uuid4(),
                project_id=job.project_id,
                scene_id=job.scene_id,
                worker_kind="tts",
                worker_name=settings.tts_worker_name,
                voice_job_id=job_id,
                payload={
                    "status": "completed",
                    "text_chars": len(text),
                    "engine": "piper",
                    "asset_url": asset_url,
                    "voice_engine": job.voice_engine,
                    "beat_durations": beat_durations,
                },
            )
            pipeline_event(
                "worker.tts",
                "job_completed",
                "Voice job and scene updated",
                voice_job_id=str(job_id),
                trace_id=tid,
                scene_id=str(job.scene_id),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Voice synthesis failed job_id=%s", job_id)
            pipeline_error(
                "worker.tts",
                "job_failed",
                "TTS pipeline raised",
                voice_job_id=str(job_id),
                trace_id=tid,
                details={"error": str(exc)[:2000]},
            )
            insert_worker_service_audit_row(
                audit_id=uuid4(),
                project_id=job.project_id,
                scene_id=job.scene_id,
                worker_kind="tts",
                worker_name=settings.tts_worker_name,
                voice_job_id=job_id,
                payload={"status": "failed", "error": str(exc)},
            )
            _fail(vstore, job_id, "tts_failed", str(exc))


def _fail(vstore: RedisVoiceJobStore, job_id: UUID, code: str, message: str) -> None:
    vstore.update(
        job_id,
        status="failed",
        progress=100,
        error_code=code,
        logs=message,
        completed_at=datetime.now(tz=UTC),
    )
    job = vstore.get(job_id)
    if job is not None:
        patch_voice_job_row(job)
