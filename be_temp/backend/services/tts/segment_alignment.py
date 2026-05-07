from __future__ import annotations

import re

from shared.schemas.voice_segments import SegmentSpan, VoiceSegmentTimestamps


def split_text_into_segments(text: str) -> list[str]:
    """Split into paragraphs first; if a single block, split into rough sentences."""
    stripped = text.strip()
    if not stripped:
        return []
    blocks = [b.strip() for b in re.split(r"\n\s*\n", stripped) if b.strip()]
    if len(blocks) > 1:
        return blocks
    # Single paragraph: split on sentence boundaries (no NLP / STT).
    rough = re.split(r"(?<=[.!?])\s+", blocks[0])
    parts = [p.strip() for p in rough if p.strip()]
    return parts if len(parts) > 1 else [blocks[0]]


def segment_time_alignment(text: str, *, total_duration_seconds: float) -> VoiceSegmentTimestamps:
    """Distribute total audio duration across paragraphs/sentences by soft character weight."""
    segments_txt = split_text_into_segments(text)
    if not segments_txt:
        return VoiceSegmentTimestamps(segments=[])
    total = max(float(total_duration_seconds), 0.05)
    weights: list[float] = []
    for s in segments_txt:
        n = max(len(s), 1)
        weights.append(n**0.85)
    wsum = sum(weights)
    durations = [total * (w / wsum) for w in weights]
    spans: list[SegmentSpan] = []
    t = 0.0
    for seg, dur in zip(segments_txt, durations, strict=True):
        dur = max(dur, 0.05)
        spans.append(SegmentSpan(text=seg, start=t, end=t + dur))
        t += dur
    return VoiceSegmentTimestamps(segments=spans)
