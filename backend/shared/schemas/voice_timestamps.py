from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WordSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    word: str = Field(min_length=1, max_length=512)
    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)

    @model_validator(mode="after")
    def end_after_start(self) -> Self:
        if self.end <= self.start:
            msg = "each word span must have end > start"
            raise ValueError(msg)
        return self


class VoiceTimestamps(BaseModel):
    """Word-level timing contract for Phase 8 sync (version 1)."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["1"] = "1"
    words: list[WordSpan] = Field(default_factory=list)

    @field_validator("words", mode="after")
    @classmethod
    def sorted_non_overlapping(cls, words: list[WordSpan]) -> list[WordSpan]:
        ordered = sorted(words, key=lambda w: w.start)
        for i in range(len(ordered) - 1):
            prev, cur = ordered[i], ordered[i + 1]
            if cur.start < prev.end - 1e-6:
                msg = "word timestamps must not overlap in time"
                raise ValueError(msg)
        return ordered
