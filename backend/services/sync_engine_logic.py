import logging
from typing import Any

from shared.schemas.planner_output import PlannerOutput
from shared.schemas.voice_segments import VoiceSegmentTimestamps

logger = logging.getLogger(__name__)


def validate_sync_duration(
    video_duration: float, audio_duration: float, threshold: float = 0.5
) -> dict:
    """
    Checks if the generated video duration matches the expected audio duration.
    """
    if video_duration is None or audio_duration is None:
        return {
            "video_duration": video_duration,
            "audio_duration": audio_duration,
            "diff": 0,
            "sync_issue": False,
            "error": "Missing duration data",
        }

    diff = abs(video_duration - audio_duration)
    is_issue = diff > threshold

    return {
        "video_duration": round(video_duration, 3),
        "audio_duration": round(audio_duration, 3),
        "diff": round(diff, 3),
        "sync_issue": is_issue,
        "threshold": threshold,
    }


def align_beats_to_audio(plan: PlannerOutput, timestamps: VoiceSegmentTimestamps) -> dict[str, Any]:
    """
    Core sync logic: Maps narrative beats from the execution plan to physical audio timestamps.
    Returns a structured 'sync_segments' dictionary.
    """
    segments = []

    # Version 2 voice timestamps provide paragraph-level 'segments'
    ts_segments = timestamps.segments

    for i, beat in enumerate(plan.beats):
        if i < len(ts_segments):
            ts = ts_segments[i]
            segments.append(
                {
                    "step_label": beat.step_label,
                    "start": ts.start,
                    "end": ts.end,
                    "duration": round(ts.end - ts.start, 3),
                    "text_ref": ts.text,
                }
            )
        else:
            # Fallback if plan has more beats than voice segments
            prev_end = segments[-1]["end"] if segments else 0.0
            segments.append(
                {
                    "step_label": beat.step_label,
                    "start": prev_end,
                    "end": prev_end + 2.0,
                    "duration": 2.0,
                    "text_ref": "[fallback/unvoiced]",
                }
            )

    return {
        "version": "1",
        "beats": segments,
        "total_audio_duration": round(ts_segments[-1].end if ts_segments else 0.0, 3),
    }
