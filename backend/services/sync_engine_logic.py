from __future__ import annotations

import logging
from typing import Any

from shared.schemas.planner_output import PlannerOutput
from shared.schemas.voice_segments import VoiceSegmentTimestamps

logger = logging.getLogger(__name__)

def align_beats_to_audio(
    plan: PlannerOutput,
    timestamps: VoiceSegmentTimestamps
) -> dict[str, float]:
    """
    Match Planner beats to Voice segments.
    Returns a dict mapping step_label to its duration.
    """
    sync_segments: dict[str, float] = {}
    
    # User requirement: "Khớp TimelineBeat.step_label với các đoạn thoại tương ứng."
    # We assume beats and segments are produced in the same order.
    
    for i, beat in enumerate(plan.beats):
        if i < len(timestamps.segments):
            seg = timestamps.segments[i]
            # Tính toán duration = end - start cho từng đoạn thoại.
            duration = seg.end - seg.start
            
            # Xử lý sai số: Nếu một Beat có nhiều Primitives, tự động phân bổ duration?
            # User example: {"intro": 2.5, "step_1": 4.2}
            sync_segments[beat.step_label] = float(round(duration, 3))
        else:
            # Fallback for extra beats
            logger.warning(f"No voice segment for beat: {beat.step_label}")
            sync_segments[beat.step_label] = 1.0
            
    return sync_segments

def validate_sync_duration(video_duration: float, audio_duration: float) -> dict[str, Any]:
    """
    Compare video duration (ffprobe) with audio duration.
    Flag sync_issue if difference > 0.2s.
    """
    diff = abs(video_duration - audio_duration)
    return {
        "is_valid": diff <= 0.2,
        "diff": float(round(diff, 3)),
        "sync_issue": diff > 0.2,
        "video_duration": video_duration,
        "audio_duration": audio_duration
    }
