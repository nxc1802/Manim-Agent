from __future__ import annotations

from backend.services.manim_validator import validate_manim_code_extended
from shared.constants import SeverityLevel


def test_manim_validator_success() -> None:
    code = """from manim import *

class GeneratedScene(Scene):
    def construct(self):
        self.play(Write(Text("Hello World")), run_time=2.0)
"""
    res = validate_manim_code_extended(code)
    assert res.passed is True
    assert len(res.issues) == 0


def test_manim_validator_missing_class() -> None:
    code = """from manim import *
# Missing GeneratedScene
"""
    res = validate_manim_code_extended(code)
    assert res.passed is False
    assert any(i.code == "missing_generated_scene" for i in res.issues)


def test_manim_validator_missing_construct() -> None:
    code = """from manim import *
class GeneratedScene(Scene):
    # Missing construct
    pass
"""
    res = validate_manim_code_extended(code)
    assert res.passed is False
    assert any(i.code == "missing_construct" for i in res.issues)


def test_manim_validator_tex_usage() -> None:
    code = """from manim import *
class GeneratedScene(Scene):
    def construct(self):
        t = Tex("forbidden")
"""
    res = validate_manim_code_extended(code)
    assert res.passed is False
    assert any(i.code == "tex_usage" and i.severity == SeverityLevel.ERROR for i in res.issues)


def test_manim_validator_unicode_superscript() -> None:
    code = """from manim import *
class GeneratedScene(Scene):
    def construct(self):
        t = Text("x² + y²")
"""
    res = validate_manim_code_extended(code)
    # Unicode superscript is a warning, so it should still pass
    assert res.passed is True
    assert any(
        i.code == "unicode_superscript" and i.severity == SeverityLevel.WARNING for i in res.issues
    )


def test_manim_validator_invalid_runtime() -> None:
    code = """from manim import *
class GeneratedScene(Scene):
    def construct(self):
        self.play(FadeIn(Text("hi")), run_time=500.0)
"""
    res = validate_manim_code_extended(code)
    # Invalid runtime is a warning
    assert res.passed is True
    assert any(
        i.code == "invalid_runtime" and i.severity == SeverityLevel.WARNING for i in res.issues
    )


def test_manim_validator_infinite_loop() -> None:
    code = """from manim import *
class GeneratedScene(Scene):
    def construct(self):
        while True:
            self.wait(1)
"""
    res = validate_manim_code_extended(code)
    assert res.passed is False
    assert any(i.code == "infinite_loop" and i.severity == SeverityLevel.ERROR for i in res.issues)


def test_manim_validator_forbidden_open() -> None:
    code = """from manim import *
class GeneratedScene(Scene):
    def construct(self):
        with open("secret.txt", "r") as f:
            pass
"""
    res = validate_manim_code_extended(code)
    assert res.passed is False
    assert any(i.code == "file_io" and i.severity == SeverityLevel.ERROR for i in res.issues)
