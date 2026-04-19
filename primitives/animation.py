from __future__ import annotations

from manim import (
    Animation,
    Circumscribe,
    FadeIn,
    FadeOut,
    Flash,
    Indicate,
    Transform,
    Write,
)
from manim.mobject.mobject import Mobject


def cinematic_fade_in(mobject: Mobject, duration: float = 0.75) -> Animation:
    return FadeIn(mobject, run_time=duration)


def cinematic_fade_out(mobject: Mobject, duration: float = 0.75) -> Animation:
    return FadeOut(mobject, run_time=duration)


def smooth_transform(
    mobject_from: Mobject,
    mobject_to: Mobject,
    duration: float = 0.9,
) -> Animation:
    return Transform(mobject_from, mobject_to, run_time=duration)


def focus_highlight(mobject: Mobject, scale_factor: float = 1.08) -> Animation:
    return Indicate(mobject, scale_factor=scale_factor)


def write_on(mobject: Mobject, run_time: float = 1.0) -> Animation:
    return Write(mobject, run_time=run_time)


def flash_attention(mobject: Mobject, line_length: float = 0.2, num_lines: int = 12) -> Animation:
    """Short burst highlight around a mobject."""
    return Flash(
        mobject,
        line_length=line_length,
        num_lines=num_lines,
        flash_radius=0.25,
        run_time=0.6,
    )


def surround_pulse(mobject: Mobject, color: str | None = None) -> Animation:
    """Emphasize a region with a circumscribe animation."""
    if color is None:
        return Circumscribe(mobject, run_time=0.9)
    return Circumscribe(mobject, color=color, run_time=0.9)
