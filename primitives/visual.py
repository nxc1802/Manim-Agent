from __future__ import annotations

from collections.abc import Sequence

from manim import (
    BLUE,
    DOWN,
    LEFT,
    RIGHT,
    UP,
    WHITE,
    Arrow,
    Code,
    Line,
    NumberLine,
    Text,
    VGroup,
)
from manim.mobject.mobject import Mobject

DEFAULT_FONT_SIZE = 40.0


def get_text_panel(text: str, color: str = BLUE, font_size: float = DEFAULT_FONT_SIZE) -> Text:
    """Readable title/body text with consistent defaults."""
    return Text(str(text), font_size=font_size, color=color)


def get_array_block(
    values: Sequence[str | float | int],
    highlight_index: int | None = 0,
    cell_font_size: float = 32.0,
) -> VGroup:
    """Horizontal row of cells; optional highlight index (negative disables)."""
    cells: list[Text] = []
    for i, v in enumerate(values):
        t = Text(str(v), font_size=cell_font_size)
        if highlight_index is not None and i == highlight_index:
            t.set_color(BLUE)
        else:
            t.set_color(WHITE)
        cells.append(t)
    group = VGroup(*cells)
    group.arrange(RIGHT, buff=0.35)
    return group


def get_code_box(code_string: str, language: str = "python") -> Code:
    """Syntax-highlighted code block (Manim `Code`)."""
    return Code(
        code_string=code_string,
        language=language,
        add_line_numbers=False,
    )


def get_title_card(title: str, subtitle: str | None = None) -> VGroup:
    """Stacked title + optional subtitle."""
    title_m = Text(str(title), font_size=48, weight="BOLD")
    parts: list[Text] = [title_m]
    if subtitle:
        parts.append(Text(str(subtitle), font_size=28).next_to(title_m, DOWN, buff=0.35))
    group = VGroup(*parts)
    group.arrange(DOWN, buff=0.25, aligned_edge=LEFT)
    return group


def get_bulleted_list(items: Sequence[str]) -> VGroup:
    """Bullet list (text-based; avoids LaTeX in CI/dev)."""
    rows = [Text(f"• {str(x)}", font_size=30) for x in items]
    group = VGroup(*rows)
    group.arrange(DOWN, buff=0.25, aligned_edge=LEFT)
    return group


def get_equation_block(latex: str) -> Mobject:
    """Equation rendering: `MathTex` when LaTeX is installed, otherwise `Text` fallback."""
    import shutil

    from manim import MathTex

    if shutil.which("latex") is not None:
        return MathTex(str(latex))
    return Text(str(latex), font_size=36, slant="ITALIC")


def get_labeled_arrow(label: str, buff: float = 0.15) -> VGroup:
    """Arrow from LEFT to RIGHT with a text label above the shaft."""
    arrow = Arrow(LEFT * 2.2, RIGHT * 2.2, buff=0.05)
    lbl = Text(str(label), font_size=28).next_to(arrow, UP, buff=buff)
    return VGroup(arrow, lbl)


def get_number_line(
    x_range: tuple[float, float, float],
    length: float = 8.0,
    include_numbers: bool = False,
) -> NumberLine:
    """Number line with tick spacing from `x_range` (start, end, step).

    Defaults to `include_numbers=False` to avoid requiring LaTeX locally/CI.
    """
    start, end, step = x_range
    return NumberLine(
        x_range=(start, end, step),
        length=length,
        include_numbers=include_numbers,
    )


def get_separator_line(width: float = 10.0, color: str = WHITE) -> Line:
    """Thin horizontal separator."""
    left = LEFT * (width / 2)
    right = RIGHT * (width / 2)
    return Line(left, right, color=color, stroke_width=2)
