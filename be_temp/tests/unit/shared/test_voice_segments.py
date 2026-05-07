from __future__ import annotations

import pytest
from pydantic import ValidationError
from shared.schemas.voice_segments import SegmentSpan, VoiceSegmentTimestamps


def test_voice_segment_timestamps_sorts_by_start() -> None:
    ts = VoiceSegmentTimestamps(
        segments=[
            SegmentSpan(text="b", start=0.5, end=0.6),
            SegmentSpan(text="a", start=0.0, end=0.4),
        ],
    )
    assert [s.text for s in ts.segments] == ["a", "b"]


def test_voice_segment_timestamps_rejects_overlap() -> None:
    with pytest.raises(ValidationError):
        VoiceSegmentTimestamps(
            segments=[
                SegmentSpan(text="a", start=0.0, end=0.5),
                SegmentSpan(text="b", start=0.3, end=0.6),
            ],
        )


def test_segment_span_rejects_end_before_start() -> None:
    with pytest.raises(ValidationError):
        SegmentSpan(text="a", start=0.5, end=0.2)
