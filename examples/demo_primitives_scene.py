"""Manual demo scene (no AI). Run locally after installing Manim:

manim -ql examples/demo_primitives_scene.py DemoPrimitivesScene
"""

from __future__ import annotations

from manim import Scene
from primitives import cinematic_fade_in, get_text_panel


class DemoPrimitivesScene(Scene):
    def construct(self) -> None:
        title = get_text_panel("Manim primitives demo", font_size=40)
        self.play(cinematic_fade_in(title, duration=0.8))
        self.wait(0.5)
