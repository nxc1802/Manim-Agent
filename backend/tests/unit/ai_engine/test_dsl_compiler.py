from __future__ import annotations

from pathlib import Path

import pytest
from ai_engine.dsl_compiler import compile_dsl_to_manim, parse_python_class_dsl
from shared.schemas.scene_dsl import (
    AnimationStep,
    CameraState,
    Position,
    SceneDSL,
    SceneDSLBeat,
    ThemeConfig,
    TransitionSpec,
    VisualElement,
)


def test_parse_python_class_dsl() -> None:
    code = """
from shared.schemas.scene_dsl import (
    AnimationStep, Position, SceneDSLBeat, ThemeConfig, VisualElement
)

class GeneratedSceneDSL:
    title = "Test DSL Scene"
    global_theme = ThemeConfig(primary_color="RED")
    beats = [
        SceneDSLBeat(
            id="beat_1",
            label="Intro Beat",
            duration_seconds=3.5,
            narration="Welcome to the demo.",
            visual_elements=[
                VisualElement(
                    id="intro_txt",
                    type="get_text_panel",
                    params={"text": "Hello DSL", "color": "RED"},
                    position=Position(x=1.0, y=2.0)
                )
            ],
            animations=[
                AnimationStep(
                    target_ids=["intro_txt"],
                    animation_type="cinematic_fade_in",
                    run_time=1.0
                )
            ]
        )
    ]
"""
    dsl = parse_python_class_dsl(code)
    assert dsl.title == "Test DSL Scene"
    assert dsl.global_theme is not None
    assert dsl.global_theme.primary_color == "RED"
    assert len(dsl.beats) == 1
    assert dsl.beats[0].id == "beat_1"
    assert dsl.beats[0].narration == "Welcome to the demo."
    assert dsl.beats[0].visual_elements[0].id == "intro_txt"
    assert dsl.beats[0].visual_elements[0].params["text"] == "Hello DSL"
    assert dsl.beats[0].animations[0].animation_type == "cinematic_fade_in"


def test_parse_python_class_dsl_never_executes_submitted_code(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    source = f"""
class GeneratedSceneDSL:
    title = "Unsafe"
    beats = []
    __import__("pathlib").Path({str(marker)!r}).touch()
"""

    with pytest.raises(ValueError, match="field assignments"):
        parse_python_class_dsl(source)
    assert not marker.exists()


def test_parse_python_class_dsl_rejects_unknown_constructor() -> None:
    source = """
class GeneratedSceneDSL:
    title = Dangerous(value="x")
    beats = []
"""
    with pytest.raises(ValueError, match="Unsupported Scene DSL constructor"):
        parse_python_class_dsl(source)


def test_compile_dsl_rejects_unknown_primitive() -> None:
    dsl = SceneDSL(
        title="Unsafe",
        beats=[
            SceneDSLBeat(
                id="beat",
                label="Beat",
                duration_seconds=1,
                visual_elements=[VisualElement(id="item", type="not_a_primitive")],
            )
        ],
    )
    with pytest.raises(ValueError, match="Unsupported visual primitive"):
        compile_dsl_to_manim(dsl)


def test_compile_dsl_to_manim() -> None:
    dsl = SceneDSL(
        title="Test Compile",
        global_theme=ThemeConfig(primary_color="BLUE"),
        beats=[
            SceneDSLBeat(
                id="beat_1",
                label="Intro",
                duration_seconds=2.0,
                narration="Intro voiceover",
                visual_elements=[
                    VisualElement(
                        id="title",
                        type="get_title_card",
                        params={"title": "Main Title", "subtitle": "Sub"},
                        position=Position(x=0.0, y=2.0),
                    ),
                    VisualElement(
                        id="body",
                        type="get_text_panel",
                        params={"text": "Body text"},
                        position=Position(relative_to="below", target_id="title", buff=0.5),
                    ),
                ],
                animations=[
                    AnimationStep(
                        target_ids=["title"],
                        animation_type="cinematic_fade_in",
                        run_time=0.8,
                    ),
                    AnimationStep(
                        target_ids=["body"],
                        animation_type="typewriter_text",
                        run_time=1.2,
                    ),
                ],
                camera=CameraState(position=(0.0, 0.0, 0.0), zoom=1.5),
                transition_out=TransitionSpec(transition_type="fade_out", duration=0.5),
            )
        ],
    )

    code = compile_dsl_to_manim(dsl)

    # General assertions
    assert "class GeneratedScene(MovingCameraScene):" in code
    assert "self.elements = {}" in code
    assert "self.elements['title'] = get_title_card(title='Main Title', subtitle='Sub')" in code
    assert "self.elements['body'] = get_text_panel(text='Body text')" in code
    assert "self.elements['title'].move_to(np.array([0.0, 2.0, 0.0]))" in code
    assert "self.elements['body'].next_to(self.elements['title'], DOWN, buff=0.5)" in code
    assert "cinematic_fade_in(self.elements['title'], duration=0.8)" in code
    assert "typewriter_text(self, self.elements['body'], run_time=1.2)" in code
    assert "self.camera.frame.move_to(np.array([0.0, 0.0, 0.0]))" in code
    assert "self.camera.frame.set_width(self.camera.frame.width / 1.5)" in code
    assert (
        "self.play(FadeOut(self.elements['title']), FadeOut(self.elements['body']), run_time=0.5)"
        in code
    )
