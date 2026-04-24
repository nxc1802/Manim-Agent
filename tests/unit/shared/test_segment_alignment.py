from __future__ import annotations

from backend.services.tts.segment_alignment import segment_time_alignment, split_text_into_segments


def test_split_paragraphs() -> None:
    parts = split_text_into_segments("Para one.\n\nPara two.")
    assert parts == ["Para one.", "Para two."]


def test_split_sentences_when_single_block() -> None:
    parts = split_text_into_segments("One. Two! Three?")
    assert parts == ["One.", "Two!", "Three?"]


def test_segment_alignment_weights() -> None:
    ts = segment_time_alignment("aa. bb.", total_duration_seconds=10.0)
    assert len(ts.segments) == 2
    assert abs(ts.segments[-1].end - 10.0) < 0.02
