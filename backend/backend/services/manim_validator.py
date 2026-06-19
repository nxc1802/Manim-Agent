from __future__ import annotations

import ast
import re

from shared.constants import SeverityLevel
from shared.schemas.validation import ValidationIssue, ValidationResult

UNICODE_SUPERSCRIPTS = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ]")


class ManimASTVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.issues: list[ValidationIssue] = []
        self.has_generated_scene = False
        self.has_construct = False

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if node.name == "GeneratedScene":
            self.has_generated_scene = True
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "construct":
                    self.has_construct = True
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in ("Tex", "MathTex"):
            self.issues.append(
                ValidationIssue(
                    code="tex_usage",
                    severity=SeverityLevel.ERROR,
                    message=f"Use of {node.id} is forbidden. Use Text, Paragraph, or MarkupText instead.",
                    line=getattr(node, "lineno", None),
                    suggestion=f"Replace {node.id} with Text or MarkupText",
                )
            )
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            if UNICODE_SUPERSCRIPTS.search(node.value):
                self.issues.append(
                    ValidationIssue(
                        code="unicode_superscript",
                        severity=SeverityLevel.WARNING,
                        message=f"Unicode superscript detected in string: {node.value!r}.",
                        line=getattr(node, "lineno", None),
                        suggestion="Use regular text or caret notation if supported.",
                    )
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        for kw in node.keywords:
            if kw.arg == "run_time":
                if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, (int, float)):
                    val = kw.value.value
                    if val < 0.01 or val > 300:
                        self.issues.append(
                            ValidationIssue(
                                code="invalid_runtime",
                                severity=SeverityLevel.WARNING,
                                message=f"run_time ({val}) is outside reasonable limits (0.01 - 300s).",
                                line=getattr(node, "lineno", None),
                                suggestion="Set run_time between 0.01 and 300 seconds.",
                            )
                        )
        if isinstance(node.func, ast.Name):
            if node.func.id == "open":
                self.issues.append(
                    ValidationIssue(
                        code="file_io",
                        severity=SeverityLevel.ERROR,
                        message="Use of open() is forbidden in sandbox.",
                        line=getattr(node, "lineno", None),
                    )
                )
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        is_always_true = False
        if isinstance(node.test, ast.Constant) and node.test.value is True:
            is_always_true = True
        elif isinstance(node.test, ast.Name) and node.test.id == "True":
            is_always_true = True

        if is_always_true:
            has_break = False
            for body_node in ast.walk(node):
                if isinstance(body_node, ast.Break):
                    has_break = True
                    break
            if not has_break:
                self.issues.append(
                    ValidationIssue(
                        code="infinite_loop",
                        severity=SeverityLevel.ERROR,
                        message="Potential infinite loop detected (while True has no break).",
                        line=getattr(node, "lineno", None),
                    )
                )
        self.generic_visit(node)


def validate_manim_code_extended(source: str) -> ValidationResult:
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return ValidationResult(
            passed=False,
            issues=[
                ValidationIssue(
                    code="syntax_error",
                    severity=SeverityLevel.ERROR,
                    message=f"Syntax error: {e.msg} at line {e.lineno}, col {e.offset}",
                    line=e.lineno,
                )
            ],
        )

    visitor = ManimASTVisitor()
    visitor.visit(tree)

    if not visitor.has_generated_scene:
        visitor.issues.append(
            ValidationIssue(
                code="missing_generated_scene",
                severity=SeverityLevel.ERROR,
                message="Class GeneratedScene is missing.",
            )
        )
    elif not visitor.has_construct:
        visitor.issues.append(
            ValidationIssue(
                code="missing_construct",
                severity=SeverityLevel.ERROR,
                message="Method construct() is missing in GeneratedScene.",
            )
        )

    passed = not any(
        i.severity in (SeverityLevel.ERROR, SeverityLevel.BLOCKER) for i in visitor.issues
    )
    return ValidationResult(passed=passed, issues=visitor.issues)
