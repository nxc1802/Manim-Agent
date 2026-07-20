from __future__ import annotations

import sys
from pathlib import Path

from app.renderer import ManimError, _get_manim_cmd, parse_manim_errors
from app.runtime_api_context import build_runtime_api_context, format_runtime_api_context


def test_renderer_uses_the_same_python_runtime_as_introspection() -> None:
    assert _get_manim_cmd() == [sys.executable, "-m", "manim"]


def test_parse_plain_traceback_preserves_scene_line_and_exception() -> None:
    stderr = '''Traceback (most recent call last):
  File "/tmp/manim_review/scene.py", line 4, in construct
    self.play(ShowCreation(Circle()))
NameError: name 'ShowCreation' is not defined
'''

    assert parse_manim_errors(stderr) == [
        ManimError(
            line=4,
            message="NameError: name 'ShowCreation' is not defined",
            error_type="NameError",
        )
    ]


def test_parse_rich_traceback_handles_wrapped_path_and_message() -> None:
    stderr = '''╭──────────────── Traceback ────────────────╮
│ /tmp/manim_review_x/scene                 │
│ .py:5 in construct                        │
│ ❱ 5 │ graph = axes.get_graph(lambda x: x) │
│ /venv/site-packages/manim/scene/scene.py:972 in compile_animations │
╰───────────────────────────────────────────╯
TypeError: Mobject.__getattr__.<locals>.getter() takes 1 positional argument but
2 were given
'''

    assert parse_manim_errors(stderr) == [
        ManimError(
            line=5,
            message=(
                "TypeError: Mobject.__getattr__.<locals>.getter() takes 1 positional "
                "argument but 2 were given"
            ),
            error_type="TypeError",
        )
    ]


def test_missing_runtime_symbol_uses_verified_compatibility_alternative() -> None:
    code = '''from manim import *
class GeneratedScene(Scene):
    def construct(self):
        self.play(ShowCreation(Circle()))
'''
    errors = [
        ManimError(
            line=4,
            message="NameError: name 'ShowCreation' is not defined",
            error_type="NameError",
        )
    ]

    context = build_runtime_api_context(code, errors)

    assert context is not None
    assert context["manim_version"]
    assert context["target_symbol"] == "ShowCreation"
    assert context["exact_api"]["exists"] is False
    assert context["alternatives"][0]["symbol"] == "Create"
    assert context["alternatives"][0]["exists"] is True
    assert "mobject" in context["alternatives"][0]["signature"]
    assert "self.play(Create(mobject))" in format_runtime_api_context(context)


def test_source_ast_resolves_bound_receiver_and_live_method_signature() -> None:
    code = '''from manim import *
class GeneratedScene(Scene):
    def construct(self):
        axes = Axes()
        graph = axes.get_graph(lambda x: x*x)
        self.add(graph)
'''
    errors = [
        ManimError(
            line=5,
            message=(
                "TypeError: Mobject.__getattr__.<locals>.getter() takes 1 positional "
                "argument but 2 were given"
            ),
            error_type="TypeError",
        )
    ]

    context = build_runtime_api_context(code, errors)

    assert context is not None
    assert context["target_symbol"] == "Axes.get_graph"
    assert context["exact_api"]["exists"] is False
    assert context["alternatives"][0]["symbol"] == "Axes.plot"
    assert "function" in context["alternatives"][0]["signature"]


def test_existing_api_context_comes_from_runtime_inspect() -> None:
    code = '''from manim import *
class GeneratedScene(Scene):
    def construct(self):
        text = Text("hello", size=32)
        self.add(text)
'''
    errors = [
        ManimError(
            line=4,
            message="TypeError: Mobject.__init__() got an unexpected keyword argument 'size'",
            error_type="TypeError",
        )
    ]

    context = build_runtime_api_context(code, errors)

    assert context is not None
    assert context["target_symbol"] == "Text"
    assert context["exact_api"]["exists"] is True
    assert "font_size" in context["exact_api"]["signature"]
    assert context["exact_api"]["summary"]
    assert context["exact_api"]["example"]


def test_plain_local_name_error_is_not_presented_as_manim_api_context() -> None:
    code = '''from manim import *
class GeneratedScene(Scene):
    def construct(self):
        self.add(local_mobject)
'''
    errors = [
        ManimError(
            line=4,
            message="NameError: name 'local_mobject' is not defined",
            error_type="NameError",
        )
    ]

    assert build_runtime_api_context(code, errors) is None


def test_compatibility_hint_is_filtered_by_runtime_version(tmp_path: Path) -> None:
    compatibility_map = tmp_path / "compatibility.yaml"
    compatibility_map.write_text(
        '''symbols:
  ShowCreation:
    alternatives:
      - symbol: Create
        min_version: "99.0.0"
        reason: not applicable
''',
        encoding="utf-8",
    )
    errors = [ManimError(line=1, message="NameError: name 'ShowCreation' is not defined")]

    context = build_runtime_api_context(
        "ShowCreation(Circle())", errors, compatibility_map_path=compatibility_map
    )

    assert context is not None
    assert context["alternatives"] == []
