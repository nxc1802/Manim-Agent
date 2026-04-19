from __future__ import annotations

import ast
from dataclasses import dataclass

FORBIDDEN_CALL_NAMES = frozenset({"exec", "eval", "__import__", "compile"})

ALLOWED_IMPORT_ROOTS = frozenset(
    {
        "__future__",
        "manim",
        "primitives",
        "typing",
        "math",
        "numpy",
    },
)


class SandboxValidationError(ValueError):
    """Raised when generated Manim code fails static safety checks."""


@dataclass(frozen=True)
class SandboxLimits:
    max_bytes: int


def _import_root(name: str) -> str:
    return name.split(".", 1)[0]


def _validate_imports(tree: ast.Module) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = _import_root(alias.name)
                if root not in ALLOWED_IMPORT_ROOTS:
                    msg = f"Disallowed import root: {root!r}"
                    raise SandboxValidationError(msg)
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                msg = "Relative imports are not allowed in generated code"
                raise SandboxValidationError(msg)
            if node.module is None:
                msg = "Wildcard or ambiguous imports are not allowed"
                raise SandboxValidationError(msg)
            root = _import_root(node.module)
            if root not in ALLOWED_IMPORT_ROOTS:
                msg = f"Disallowed import-from module root: {root!r}"
                raise SandboxValidationError(msg)
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALL_NAMES:
                msg = f"Disallowed call: {func.id}()"
                raise SandboxValidationError(msg)


def _validate_generated_scene_class(tree: ast.Module) -> None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "GeneratedScene":
            return
    msg = "Generated code must define class GeneratedScene"
    raise SandboxValidationError(msg)


def validate_manim_code(source: str, *, limits: SandboxLimits) -> None:
    """Static checks: size, syntax, import policy, required class name."""
    data = source.encode("utf-8")
    if len(data) > limits.max_bytes:
        msg = f"Code exceeds max size ({limits.max_bytes} bytes)"
        raise SandboxValidationError(msg)
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        msg = f"Invalid Python syntax: {exc.msg}"
        raise SandboxValidationError(msg) from exc
    if not isinstance(tree, ast.Module):
        msg = "Expected a module"
        raise SandboxValidationError(msg)
    _validate_imports(tree)
    _validate_generated_scene_class(tree)


def static_check_split(source: str, *, limits: SandboxLimits) -> tuple[bool, bool, str | None]:
    """Return (syntax_ok, policy_ok, error_code).

    ``syntax_ok`` means Python parses. ``policy_ok`` adds import rules + GeneratedScene class.
    """
    data = source.encode("utf-8")
    if len(data) > limits.max_bytes:
        return False, False, "size_exceeded"
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False, False, "syntax_error"
    if not isinstance(tree, ast.Module):
        return False, False, "syntax_error"
    try:
        _validate_imports(tree)
        _validate_generated_scene_class(tree)
    except SandboxValidationError:
        return True, False, "policy_error"
    return True, True, None
