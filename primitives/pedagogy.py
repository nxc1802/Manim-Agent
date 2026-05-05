from __future__ import annotations

import shutil
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from manim import Scene, Mobject, ValueTracker

# Pedagogical patterns extracted from 3Blue1Brown style, native on ManimCE.

def equation_morph(scene: Scene, text_from: str, text_to: str, run_time: float = 1.5) -> None:
    """3B1B-style equation transformation using ManimCE TransformMatchingTex."""
    from manim import Text, ReplacementTransform
    
    # Check if LaTeX is installed to use TransformMatchingTex
    if shutil.which("latex"):
        try:
            from manim import MathTex, TransformMatchingTex
            eq1 = MathTex(text_from)
            eq2 = MathTex(text_to)
            scene.play(TransformMatchingTex(eq1, eq2), run_time=run_time)
            return
        except Exception:
            pass
            
    # Fallback: Text-based transform (safer for environments without LaTeX)
    t1 = Text(text_from, font_size=36)
    t2 = Text(text_to, font_size=36)
    scene.play(ReplacementTransform(t1, t2), run_time=run_time)


def progressive_reveal(scene: Scene, group: Sequence[Mobject], lag_ratio: float = 0.15) -> None:
    """Staggered entrance of multiple mobjects."""
    from manim import FadeIn, LaggedStart
    scene.play(LaggedStart(*[FadeIn(m) for m in group], lag_ratio=lag_ratio))


def progressive_remove(scene: Scene, group: Sequence[Mobject], lag_ratio: float = 0.15) -> None:
    """Staggered exit of multiple mobjects."""
    from manim import FadeOut, LaggedStart
    scene.play(LaggedStart(*[FadeOut(m) for m in group], lag_ratio=lag_ratio))


def counter_animate(
    scene: Scene, 
    start_val: float, 
    end_val: float, 
    duration: float = 2.0,
    label_prefix: str = "",
    font_size: float = 48.0
) -> None:
    """Animated counting number using ValueTracker."""
    from manim import DecimalNumber, ValueTracker, always_redraw, Text, VGroup, RIGHT, LEFT
    
    tracker = ValueTracker(start_val)
    number = DecimalNumber(start_val).scale(1.5)
    number.add_updater(lambda m: m.set_value(tracker.get_value()))
    
    if label_prefix:
        lbl = Text(label_prefix, font_size=font_size)
        group = VGroup(lbl, number).arrange(RIGHT, buff=0.2)
        scene.add(group)
    else:
        scene.add(number)
        
    scene.play(tracker.animate.set_value(end_val), run_time=duration)


def theorem_reveal(scene: Scene, statement: str, proof_steps: Sequence[Mobject]) -> None:
    """Reveal a theorem statement then its proof steps sequentially."""
    from manim import Text, Write, DOWN, LEFT
    
    title = Text(statement, font_size=40, color="#FFFF00").to_edge(UP)
    scene.play(Write(title))
    scene.wait(0.5)
    
    if proof_steps:
        # Align proof steps below title
        last = title
        for step in proof_steps:
            step.next_to(last, DOWN, buff=0.4, aligned_edge=LEFT)
            scene.play(FadeIn(step, shift=DOWN*0.2))
            last = step


def graph_trace(
    scene: Scene, 
    axes: Any, 
    func: Callable[[float], float], 
    x_range: Sequence[float], 
    color: str = "#58C4DD",
    run_time: float = 2.0
) -> None:
    """Draw a function graph progressively on given axes."""
    from manim import Create
    graph = axes.plot(func, x_range=x_range, color=color)
    scene.play(Create(graph), run_time=run_time)


def notation_swap(scene: Scene, mob_from: Mobject, mob_to: Mobject, run_time: float = 1.0) -> None:
    """Smooth replacement of one mobject with another (cross-fade)."""
    from manim import FadeTransform
    scene.play(FadeTransform(mob_from, mob_to), run_time=run_time)
