from __future__ import annotations

import pytest
from backend.core.config import settings
from backend.services.code_sandbox import SandboxLimits, SandboxValidationError, validate_manim_code

_VALID = """from __future__ import annotations

from manim import Scene


class GeneratedScene(Scene):
    def construct(self) -> None:
        self.wait(0.1)
"""


def test_validate_manim_code_accepts_minimal_scene() -> None:
    validate_manim_code(
        _VALID,
        limits=SandboxLimits(max_bytes=settings.max_manim_code_bytes),
    )


def test_validate_rejects_forbidden_import() -> None:
    bad = _VALID + "\nimport os\n"
    with pytest.raises(SandboxValidationError, match="Disallowed import"):
        validate_manim_code(bad, limits=SandboxLimits(max_bytes=10_000))


def test_validate_rejects_exec() -> None:
    bad = _VALID.replace("self.wait(0.1)", "exec('1')")
    with pytest.raises(SandboxValidationError, match="Disallowed call"):
        validate_manim_code(bad, limits=SandboxLimits(max_bytes=10_000))


def test_validate_rejects_missing_generated_scene_class() -> None:
    bad = (
        "from manim import Scene\n\n"
        "class Other(Scene):\n"
        "    def construct(self) -> None:\n"
        "        pass\n"
    )
    with pytest.raises(SandboxValidationError, match="GeneratedScene"):
        validate_manim_code(bad, limits=SandboxLimits(max_bytes=10_000))


def test_validate_rejects_oversized_source() -> None:
    huge = _VALID + ("#" * (settings.max_manim_code_bytes + 10))
    with pytest.raises(SandboxValidationError, match="max size"):
        validate_manim_code(huge, limits=SandboxLimits(max_bytes=settings.max_manim_code_bytes))
