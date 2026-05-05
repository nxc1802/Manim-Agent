from __future__ import annotations

from typing import TYPE_CHECKING, Sequence, Any
if TYPE_CHECKING:
    from manim import Scene, Mobject, Animation

from manim import (
    Animation,
    Circumscribe,
    FadeIn,
    FadeOut,
    Flash,
    Indicate,
    Transform,
    ReplacementTransform,
    Write,
    UP,
    DOWN,
    RIGHT,
    LEFT
)
from manim.mobject.mobject import Mobject


def cinematic_fade_in(mobject: Mobject, duration: float = 0.75) -> Animation:
    return FadeIn(mobject, run_time=duration)


def cinematic_entrance(mobject: Mobject, duration: float = 0.8) -> Animation:
    """3B1B-style entrance: FadeIn + Shift up."""
    from manim import smooth
    return FadeIn(mobject, shift=UP * 0.3, run_time=duration, rate_func=smooth)


def cinematic_fade_out(mobject: Mobject, duration: float = 0.75) -> Animation:
    return FadeOut(mobject, run_time=duration)


def smooth_transform(
    mobject_from: Mobject,
    mobject_to: Mobject,
    duration: float = 0.9,
) -> Animation:
    """ReplacementTransform for cleaner mobject management."""
    return ReplacementTransform(mobject_from, mobject_to, run_time=duration)


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


def cascade_fade_in(scene: Scene, group: Sequence[Mobject], lag_ratio: float = 0.1, direction: Any = DOWN * 0.2) -> None:
    """Staggered entrance from a specific direction."""
    from manim import FadeIn, LaggedStart
    scene.play(LaggedStart(*[FadeIn(m, shift=direction) for m in group], lag_ratio=lag_ratio))


def cascade_fade_out(scene: Scene, group: Sequence[Mobject], lag_ratio: float = 0.05) -> None:
    """Staggered exit of multiple mobjects."""
    from manim import FadeOut, LaggedStart
    scene.play(LaggedStart(*[FadeOut(m) for m in group], lag_ratio=lag_ratio))


def focus_zoom(scene: Scene, target: Mobject, zoom_factor: float = 0.5, duration: float = 1.5) -> None:
    """Camera zoom into a specific target mobject. Requires scene to be a MovingCameraScene."""
    try:
        scene.play(scene.camera.frame.animate.set_width(target.width / zoom_factor).move_to(target), run_time=duration)
    except AttributeError:
        # Fallback if not a MovingCameraScene: just indicate
        scene.play(Indicate(target), run_time=duration)


def sweep_reveal(scene: Scene, mobject: Mobject, direction: Any = RIGHT, run_time: float = 1.0) -> None:
    """Reveal a mobject with a directional shift."""
    from manim import FadeIn
    scene.play(FadeIn(mobject, shift=direction), run_time=run_time)


def typewriter_text(scene: Scene, text: str | Mobject, run_time: float = 2.0) -> None:
    """Character-by-character text appearance."""
    from manim import AddTextLetterByLetter, Text
    if isinstance(text, str):
        text = Text(text, font_size=32)
    scene.play(AddTextLetterByLetter(text), run_time=run_time)


def wave_emphasis(scene: Scene, target: Mobject, run_time: float = 1.0) -> None:
    """Apply a wave animation to emphasize a mobject."""
    from manim import ApplyWave
    scene.play(ApplyWave(target), run_time=run_time)


def highlight_region(mobject: Mobject, opacity: float = 0.7) -> Mobject:
    """Focus effect: returns a Cutout (dimmer) mobject.
    
    Builder must call self.play(FadeIn(dimmer)) and can later remove it.
    """
    from manim import BLACK, Cutout, FullScreenRectangle, Rectangle
    
    hole = Rectangle(
        width=mobject.width + 0.6,
        height=mobject.height + 0.6,
        stroke_width=0,
        fill_opacity=0
    ).move_to(mobject)
    
    background = FullScreenRectangle(fill_color=BLACK, fill_opacity=opacity, stroke_width=0)
    dimmer = Cutout(background, hole, fill_color=BLACK, fill_opacity=opacity, stroke_width=0)
    
    return dimmer
