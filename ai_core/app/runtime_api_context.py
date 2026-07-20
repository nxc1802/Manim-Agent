"""Authoritative Manim API context sourced from the running worker runtime.

The reviewer must not guess which Manim API is installed.  This module resolves
the symbol implicated by a render failure, inspects the object imported by the
same Python process that launches Manim, and renders a bounded prompt section.
Compatibility suggestions are curated separately and are only returned when
their declared version range matches *and* the replacement exists at runtime.
"""

from __future__ import annotations

import ast
import inspect
import re
import sys
import textwrap
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.renderer import ManimError

_COMPATIBILITY_MAP_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "manim_compatibility.yaml"
)
_SYMBOL_RE = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$")


def build_runtime_api_context(
    code: str,
    errors: list[ManimError | dict[str, Any]],
    *,
    compatibility_map_path: Path | None = None,
) -> dict[str, Any] | None:
    """Build runtime-verified API context for the primary render error.

    Returns ``None`` when the traceback/source does not identify a plausible
    Manim symbol.  No arbitrary expression is evaluated: resolution walks
    identifier-only attributes starting at the imported ``manim`` module.
    """
    if not errors:
        return None

    primary = errors[0]
    line = primary.line if isinstance(primary, ManimError) else primary.get("line")
    message = (
        primary.message
        if isinstance(primary, ManimError)
        else str(primary.get("message") or primary.get("description") or "")
    )
    target, source_line, discovery = _identify_target(code, line, message)
    if not target or not _SYMBOL_RE.fullmatch(target):
        return None

    import manim

    version = str(getattr(manim, "__version__", "unknown"))
    exact_api = _introspect_symbol(version, target)
    entries = _load_compatibility_map(compatibility_map_path or _COMPATIBILITY_MAP_PATH)
    entry = entries.get(target)
    if not exact_api["exists"] and not isinstance(entry, dict):
        if discovery == "traceback_name_error" and not _is_ast_api_position(
            code, line, target
        ):
            # A plain undefined local variable is not Manim API evidence.
            return None
        if discovery == "traceback_attribute_error" and "." in target:
            owner = target.rsplit(".", 1)[0]
            if not _introspect_symbol(version, owner)["exists"]:
                # Do not present a user-defined/local class as a Manim class.
                return None
    alternatives: list[dict[str, Any]] = []
    if not exact_api["exists"]:
        if isinstance(entry, dict):
            for alternative in entry.get("alternatives", []):
                if not isinstance(alternative, dict):
                    continue
                if not _version_in_range(
                    version,
                    minimum=alternative.get("min_version"),
                    maximum_exclusive=alternative.get("max_version_exclusive"),
                ):
                    continue
                symbol = str(alternative.get("symbol") or "")
                if not _SYMBOL_RE.fullmatch(symbol):
                    continue
                inspected = _introspect_symbol(version, symbol)
                # A compatibility hint is authoritative only when the proposed
                # replacement can be resolved in this exact runtime.
                if not inspected["exists"]:
                    continue
                inspected = dict(inspected)
                inspected["reason"] = str(alternative.get("reason") or "")
                if alternative.get("example"):
                    inspected["example"] = str(alternative["example"])
                    inspected["example_source"] = "compatibility_map"
                alternatives.append(inspected)

    return {
        "manim_version": version,
        "python_executable": sys.executable,
        "target_symbol": target,
        "target_discovery": discovery,
        "source_line": source_line,
        "exact_api": dict(exact_api),
        "alternatives": alternatives,
    }


def format_runtime_api_context(context: dict[str, Any] | None) -> str:
    """Render a bounded, explicit source-of-truth section for the reviewer."""
    if not context:
        return ""
    exact = context.get("exact_api") or {}
    lines = [
        "<RUNTIME_MANIM_API_CONTEXT>",
        "This block is authoritative runtime introspection, not model knowledge.",
        f"Manim version: {context.get('manim_version', 'unknown')}",
        f"Python runtime: {context.get('python_executable', 'unknown')}",
        f"Failing symbol: {context.get('target_symbol', 'unknown')}",
    ]
    if context.get("source_line"):
        lines.append(f"Observed source line: {context['source_line']}")
    lines.append(f"Symbol exists in this runtime: {bool(exact.get('exists'))}")
    if exact.get("exists"):
        lines.extend(_format_reference(exact))
    else:
        alternatives = context.get("alternatives") or []
        if alternatives:
            lines.append("Verified compatibility alternatives:")
            for alternative in alternatives:
                lines.append(f"- {alternative.get('symbol')}: {alternative.get('reason', '')}")
                lines.extend(f"  {line}" for line in _format_reference(alternative))
        else:
            lines.append("No version-compatible replacement is present in the curated map.")
    lines.extend(
        [
            "Use only APIs verified above; do not invent a missing function or class.",
            "</RUNTIME_MANIM_API_CONTEXT>",
        ]
    )
    return "\n".join(lines)[:8_000]


def _format_reference(reference: dict[str, Any]) -> list[str]:
    lines = [f"API: {reference.get('symbol')}"]
    if reference.get("signature"):
        lines.append(f"Signature: {reference['signature']}")
    if reference.get("summary"):
        lines.append(f"Description: {reference['summary']}")
    if reference.get("example"):
        source = reference.get("example_source") or "runtime_docstring"
        lines.append(f"Usage example ({source}):\n{reference['example']}")
    return lines


def _identify_target(code: str, line: int | None, message: str) -> tuple[str | None, str | None, str]:
    source_line = _source_line(code, line)

    match = re.search(r"NameError:\s*name ['\"]([A-Za-z_]\w*)['\"] is not defined", message)
    if match:
        return match.group(1), source_line, "traceback_name_error"

    match = re.search(r"cannot import name ['\"]([A-Za-z_]\w*)['\"] from ['\"]manim", message)
    if match:
        return match.group(1), source_line, "traceback_import_error"

    match = re.search(
        r"AttributeError:\s*['\"]([A-Za-z_]\w*)['\"] object has no attribute ['\"]([A-Za-z_]\w*)['\"]",
        message,
    )
    if match:
        return f"{match.group(1)}.{match.group(2)}", source_line, "traceback_attribute_error"

    match = re.search(
        r"(?:module ['\"]manim['\"]|type object ['\"]([A-Za-z_]\w*)['\"]).*?"
        r"has no attribute ['\"]([A-Za-z_]\w*)['\"]",
        message,
    )
    if match:
        owner = match.group(1)
        return f"{owner}.{match.group(2)}" if owner else match.group(2), source_line, "traceback_attribute_error"

    keyword_match = re.search(r"unexpected keyword argument ['\"]([A-Za-z_]\w*)['\"]", message)
    source_target = _target_from_source(code, line, keyword=keyword_match.group(1) if keyword_match else None)
    if source_target:
        return source_target, source_line, "source_ast"

    match = re.search(
        r"(?:TypeError|ValueError):\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)\(\)", message
    )
    if match:
        target = match.group(1)
        if target.endswith(".__init__"):
            target = target.removesuffix(".__init__")
        return target, source_line, "traceback_callable"
    return None, source_line, "unresolved"


def _target_from_source(code: str, line: int | None, *, keyword: str | None) -> str | None:
    if line is None:
        return None
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    bindings = _constructor_bindings(tree, line)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and node.lineno <= line <= getattr(node, "end_lineno", node.lineno)
    ]
    if keyword:
        matching = [
            call
            for call in calls
            if any(item.arg == keyword for item in call.keywords if item.arg is not None)
        ]
        if matching:
            calls = matching
    # The innermost call normally identifies the API that consumed the bad
    # argument, while wrapper calls such as self.play(...) are less useful.
    calls.sort(key=lambda node: (getattr(node, "end_col_offset", 0) - node.col_offset, node.col_offset))
    for call in calls:
        symbol = _call_symbol(call.func, bindings)
        if symbol and not symbol.startswith("self.") and _SYMBOL_RE.fullmatch(symbol):
            return symbol
    return None


def _is_ast_api_position(code: str, line: int | None, target: str) -> bool:
    """Return true only when an unresolved name is used as a callable/class."""
    if line is None:
        return False
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and node.lineno <= line <= getattr(
            node, "end_lineno", node.lineno
        ):
            if _raw_symbol(node.func) == target:
                return True
        if isinstance(node, ast.ClassDef) and node.lineno == line:
            if any(_raw_symbol(base) == target for base in node.bases):
                return True
    return False


def _constructor_bindings(tree: ast.AST, before_line: int) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.lineno >= before_line:
            continue
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        constructor = _raw_symbol(value.func)
        if not constructor or constructor.startswith("self."):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                bindings[target.id] = constructor
    return bindings


def _call_symbol(node: ast.expr, bindings: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return bindings.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        owner = _raw_symbol(node.value)
        if owner in bindings:
            owner = bindings[owner]
        return f"{owner}.{node.attr}" if owner else node.attr
    return None


def _raw_symbol(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _raw_symbol(node.value)
        return f"{owner}.{node.attr}" if owner else node.attr
    return None


def _source_line(code: str, line: int | None) -> str | None:
    if line is None:
        return None
    lines = code.splitlines()
    if 1 <= line <= len(lines):
        return lines[line - 1].strip()[:500]
    return None


@lru_cache(maxsize=256)
def _introspect_symbol(version: str, symbol: str) -> dict[str, Any]:
    # ``version`` is intentionally part of the cache key. A long-running worker
    # cannot accidentally reuse context after its runtime image is upgraded.
    _ = version
    import manim

    obj: Any = manim
    try:
        for part in symbol.removeprefix("manim.").split("."):
            obj = getattr(obj, part)
    except AttributeError:
        return {
            "symbol": symbol,
            "exists": False,
            "signature": None,
            "summary": None,
            "example": None,
            "example_source": None,
        }

    try:
        signature = str(inspect.signature(obj))
    except (TypeError, ValueError):
        signature = None
    doc = inspect.getdoc(obj) or ""
    summary = _doc_summary(doc)
    example = _doc_example(doc)
    example_source = "runtime_docstring" if example else None
    if not example and signature:
        example = _usage_shape(symbol, inspect.signature(obj))
        example_source = "runtime_signature" if example else None
    return {
        "symbol": symbol,
        "exists": True,
        "signature": signature,
        "summary": summary,
        "example": example,
        "example_source": example_source,
        "module": str(getattr(obj, "__module__", "manim")),
    }


def _doc_summary(doc: str) -> str | None:
    if not doc:
        return None
    paragraph = re.split(r"\n\s*\n|\nParameters\n[-]+", doc, maxsplit=1)[0]
    summary = " ".join(paragraph.split())
    return summary[:600] or None


def _doc_example(doc: str) -> str | None:
    match = re.search(r"\nExamples?\n[-]+\n(?P<body>.*)", doc, flags=re.DOTALL)
    if not match:
        return None
    body = match.group("body")
    lines = body.splitlines()
    code_lines: list[str] = []
    started = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(".. manim::"):
            if started:
                break
            continue
        if not started and (stripped.startswith(":") or not stripped):
            continue
        if stripped.startswith("class ") or started:
            started = True
            if stripped.startswith(".. ") and code_lines:
                break
            code_lines.append(line)
            if len(code_lines) >= 18:
                break
    if not code_lines:
        return None
    return textwrap.dedent("\n".join(code_lines)).strip()[:1_600] or None


def _usage_shape(symbol: str, signature: inspect.Signature) -> str | None:
    arguments: list[str] = []
    for parameter in signature.parameters.values():
        if parameter.name in {"self", "cls"}:
            continue
        if parameter.default is not inspect.Parameter.empty:
            continue
        if parameter.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }:
            continue
        annotation = str(parameter.annotation)
        if "str" in annotation:
            arguments.append('"text"')
        elif "Callable" in annotation:
            arguments.append("lambda x: x")
        elif "float" in annotation:
            arguments.append("1.0")
        elif "int" in annotation:
            arguments.append("1")
        else:
            arguments.append(parameter.name)
    if "." in symbol:
        owner, method = symbol.rsplit(".", 1)
        receiver = re.sub(r"(?<!^)(?=[A-Z])", "_", owner.rsplit(".", 1)[-1]).lower()
        return f"{receiver}.{method}({', '.join(arguments)})"
    return f"{symbol}({', '.join(arguments)})"


@lru_cache(maxsize=8)
def _load_compatibility_map(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    entries = payload.get("symbols")
    return entries if isinstance(entries, dict) else {}


def _version_in_range(
    version: str,
    *,
    minimum: object = None,
    maximum_exclusive: object = None,
) -> bool:
    current = _version_tuple(version)
    if minimum is not None and current < _version_tuple(str(minimum)):
        return False
    if maximum_exclusive is not None and current >= _version_tuple(str(maximum_exclusive)):
        return False
    return True


def _version_tuple(version: str) -> tuple[int, int, int]:
    numbers = [int(item) for item in re.findall(r"\d+", version)[:3]]
    return tuple((numbers + [0, 0, 0])[:3])  # type: ignore[return-value]
