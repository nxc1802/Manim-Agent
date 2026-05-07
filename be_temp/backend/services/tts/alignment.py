from __future__ import annotations

from shared.schemas.voice_timestamps import VoiceTimestamps, WordSpan


def naive_word_alignment(text: str, *, total_duration_seconds: float) -> VoiceTimestamps:
    """Split plain text into equal-length per-word spans (fallback when provider has no marks)."""
    words = [w.strip(".,;:!?\"'") for w in text.split() if w.strip()]
    if not words:
        return VoiceTimestamps(words=[])
    n = len(words)
    dur = max(total_duration_seconds / n, 0.05)
    spans: list[WordSpan] = []
    t = 0.0
    for w in words:
        spans.append(WordSpan(word=w, start=t, end=t + dur))
        t += dur
    return VoiceTimestamps(words=spans)
