from __future__ import annotations

import pytest
from backend.services.code_sandbox import (
    SandboxLimits,
    SandboxValidationError,
    static_check_split,
    validate_manim_code,
)


def test_validate_manim_code_success():
    code = "from manim import *\nclass GeneratedScene(Scene):\n    pass"
    validate_manim_code(code, limits=SandboxLimits(max_bytes=1000))


def test_validate_manim_code_size_fail():
    code = "x = 1"
    with pytest.raises(SandboxValidationError, match="Code exceeds max size"):
        validate_manim_code(code, limits=SandboxLimits(max_bytes=2))


def test_validate_manim_code_syntax_fail():
    code = "class GeneratedScene(Scene)"  # missing colon
    with pytest.raises(SandboxValidationError, match="Invalid Python syntax"):
        validate_manim_code(code, limits=SandboxLimits(max_bytes=1000))


def test_validate_manim_code_policy_fail():
    # Disallowed import
    code = "import os\nclass GeneratedScene(Scene): pass"
    with pytest.raises(SandboxValidationError, match="Disallowed import root"):
        validate_manim_code(code, limits=SandboxLimits(max_bytes=1000))

    # Relative import
    code = "from . import x\nclass GeneratedScene(Scene): pass"
    with pytest.raises(SandboxValidationError, match="Relative imports are not allowed"):
        validate_manim_code(code, limits=SandboxLimits(max_bytes=1000))

    # Forbidden call
    code = "exec('ls')\nclass GeneratedScene(Scene): pass"
    with pytest.raises(SandboxValidationError, match="Disallowed call"):
        validate_manim_code(code, limits=SandboxLimits(max_bytes=1000))

    # Missing class
    code = "class WrongClass(Scene): pass"
    with pytest.raises(SandboxValidationError, match="must define class GeneratedScene"):
        validate_manim_code(code, limits=SandboxLimits(max_bytes=1000))


def test_static_check_split():
    limits = SandboxLimits(max_bytes=1000)

    # OK
    ok, pol, err = static_check_split(
        "from manim import *\nclass GeneratedScene(Scene): pass", limits=limits
    )
    assert ok and pol and err is None

    # Syntax fail
    ok, pol, err = static_check_split("invalid syntax", limits=limits)
    assert not ok and not pol and err == "syntax_error"

    # Policy fail
    ok, pol, err = static_check_split("import os\nclass GeneratedScene(Scene): pass", limits=limits)
    assert ok and not pol and err == "policy_error"

    # Size fail
    ok, pol, err = static_check_split("x = 1", limits=SandboxLimits(max_bytes=1))
    assert not ok and not pol and err == "size_exceeded"
