from __future__ import annotations

import pytest
from pydantic import ValidationError
from shared.schemas.voice_timestamps import VoiceTimestamps, WordSpan


def test_voice_timestamps_sorts_by_start() -> None:
    ts = VoiceTimestamps(
        words=[
            WordSpan(word="b", start=0.5, end=0.6),
            WordSpan(word="a", start=0.0, end=0.4),
        ],
    )
    assert [w.word for w in ts.words] == ["a", "b"]


def test_voice_timestamps_rejects_overlap() -> None:
    with pytest.raises(ValidationError):
        VoiceTimestamps(
            words=[
                WordSpan(word="a", start=0.0, end=0.5),
                WordSpan(word="b", start=0.3, end=0.6),
            ],
        )


def test_voice_timestamps_rejects_end_before_start() -> None:
    with pytest.raises(ValidationError):
        WordSpan(word="a", start=0.5, end=0.2)


def test_voice_timestamps_allows_adjacent_spans() -> None:
    ts = VoiceTimestamps(
        words=[
            WordSpan(word="a", start=0.0, end=0.1),
            WordSpan(word="b", start=0.1, end=0.2),
        ],
    )
    assert len(ts.words) == 2
