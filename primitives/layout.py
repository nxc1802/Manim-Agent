from __future__ import annotations

from manim import DOWN, RIGHT, SMALL_BUFF, WHITE, SurroundingRectangle, VGroup
from manim.mobject.mobject import Mobject


def stack_horizontal(*mobjects: Mobject, buff: float = 0.35) -> VGroup:
    """Arrange mobjects left-to-right."""
    group = VGroup(*mobjects)
    group.arrange(RIGHT, buff=buff)
    return group


def stack_vertical(*mobjects: Mobject, buff: float = 0.35) -> VGroup:
    """Arrange mobjects top-to-bottom."""
    group = VGroup(*mobjects)
    group.arrange(DOWN, buff=buff)
    return group


def center_mobject(mobject: Mobject) -> Mobject:
    """Center about origin (mutates and returns the same instance)."""
    mobject.center()
    return mobject


def surround_with_frame(
    mobject: Mobject,
    buff: float = SMALL_BUFF,
    color: str = WHITE,
) -> SurroundingRectangle:
    """Rectangle frame around a mobject."""
    return SurroundingRectangle(mobject, buff=buff, color=color)


def scale_to_width(mobject: Mobject, width: float) -> Mobject:
    """Uniformly scale to target width (mutates and returns the same instance)."""
    mobject.scale_to_fit_width(float(width))
    return mobject
