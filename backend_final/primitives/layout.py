from __future__ import annotations

from collections.abc import Sequence

from manim import DOWN, RIGHT, SMALL_BUFF, WHITE, SurroundingRectangle, VGroup
from manim.mobject.mobject import Mobject


def stack_horizontal(*mobjects: Mobject | Sequence[Mobject], buff: float = 0.35) -> VGroup:
    """Arrange mobjects left-to-right. Supports both *args and a single list/tuple."""
    if len(mobjects) == 1 and isinstance(mobjects[0], (list, tuple)):
        objs = mobjects[0]
    else:
        objs = mobjects
    group = VGroup(*objs)
    group.arrange(RIGHT, buff=buff)
    return group


def stack_vertical(*mobjects: Mobject | Sequence[Mobject], buff: float = 0.35) -> VGroup:
    """Arrange mobjects top-to-bottom. Supports both *args and a single list/tuple."""
    if len(mobjects) == 1 and isinstance(mobjects[0], (list, tuple)):
        objs = mobjects[0]
    else:
        objs = mobjects
    group = VGroup(*objs)
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
