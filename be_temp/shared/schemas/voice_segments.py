from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SegmentSpan(BaseModel):
    """Coarse timing for a paragraph or sentence block (no STT, no word marks)."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=50_000)
    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)

    @model_validator(mode="after")
    def end_after_start(self) -> Self:
        if self.end <= self.start:
            msg = "each segment span must have end > start"
            raise ValueError(msg)
        return self


class VoiceSegmentTimestamps(BaseModel):
    """Version 2: paragraph/sentence-level timing (fallback when no word-level marks)."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["2"] = "2"
    granularity: Literal["segment"] = "segment"
    segments: list[SegmentSpan] = Field(default_factory=list)

    @field_validator("segments", mode="after")
    @classmethod
    def sorted_non_overlapping(cls, segments: list[SegmentSpan]) -> list[SegmentSpan]:
        ordered = sorted(segments, key=lambda s: s.start)
        for i in range(len(ordered) - 1):
            prev, cur = ordered[i], ordered[i + 1]
            if cur.start < prev.end - 1e-6:
                msg = "segment timestamps must not overlap in time"
                raise ValueError(msg)
        return ordered
