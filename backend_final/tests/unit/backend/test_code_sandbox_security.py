from __future__ import annotations

import pytest
from backend.services.code_sandbox import (
    SandboxLimits,
    SandboxValidationError,
    validate_manim_code,
)


def test_validate_manim_code_accepts_good_code() -> None:
    code = """
from manim import *
from primitives import *

class GeneratedScene(Scene):
    def construct(self):
        self.add(Circle())
"""
    limits = SandboxLimits(max_bytes=1000)
    # Should not raise
    validate_manim_code(code, limits=limits)


def test_validate_manim_code_rejects_forbidden_imports() -> None:
    code = """
import os
import subprocess
from manim import Scene

class GeneratedScene(Scene):
    def construct(self):
        os.system("ls")
"""
    limits = SandboxLimits(max_bytes=1000)
    with pytest.raises(SandboxValidationError, match="Disallowed import root: 'os'"):
        validate_manim_code(code, limits=limits)


def test_validate_manim_code_rejects_forbidden_calls() -> None:
    code = """
from manim import Scene

class GeneratedScene(Scene):
    def construct(self):
        eval("1 + 1")
"""
    limits = SandboxLimits(max_bytes=1000)
    with pytest.raises(SandboxValidationError, match="Disallowed call: eval"):
        validate_manim_code(code, limits=limits)


def test_validate_manim_code_rejects_large_code() -> None:
    code = "x = 1\n" * 100
    limits = SandboxLimits(max_bytes=10)
    with pytest.raises(SandboxValidationError, match="Code exceeds max size"):
        validate_manim_code(code, limits=limits)


def test_validate_manim_code_requires_generated_scene_class() -> None:
    code = """
from manim import Scene

class MyScene(Scene):
    def construct(self):
        pass
"""
    limits = SandboxLimits(max_bytes=1000)
    with pytest.raises(
        SandboxValidationError, match="Generated code must define class GeneratedScene"
    ):
        validate_manim_code(code, limits=limits)


@pytest.mark.parametrize(
    "malicious",
    [
        "import socket",
        "import requests",
        "from os import path",
        "import sys",
        "exec('print(1)')",
        "__import__('os').system('ls')",
    ],
)
def test_various_malicious_attempts(malicious: str) -> None:
    code = f"""
from manim import Scene
{malicious}
class GeneratedScene(Scene):
    def construct(self):
        pass
"""
    limits = SandboxLimits(max_bytes=1000)
    with pytest.raises(SandboxValidationError):
        validate_manim_code(code, limits=limits)
