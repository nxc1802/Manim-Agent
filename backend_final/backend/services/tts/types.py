from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class TTSResult:
    """Output of a TTS synthesis call."""

    audio_url: str
    audio_format: Literal["mp3", "wav", "ogg"]
    timestamps: dict[str, Any]
    duration_seconds: float | None
