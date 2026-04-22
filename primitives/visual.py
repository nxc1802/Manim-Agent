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
    import shutil
    start, end, step = x_range
    # Safe fallback: if LaTeX is missing, force include_numbers=False to prevent crash.
    safe_include = include_numbers and (shutil.which("latex") is not None)
    return NumberLine(
        x_range=(start, end, step),
        length=length,
        include_numbers=safe_include,
    )


def get_separator_line(width: float = 10.0, color: str = WHITE) -> Line:
    """Thin horizontal separator."""
    left = LEFT * (width / 2)
    right = RIGHT * (width / 2)
    return Line(left, right, color=color, stroke_width=2)


def get_data_chart(
    values: Sequence[float],
    labels: Sequence[str] | None = None,
    max_height: float = 4.0,
    width: float = 8.0,
    color: str = BLUE,
) -> VGroup:
    """Simple bar chart using Rectangles and Text labels."""
    from manim import ORIGIN, Rectangle
    
    if not values:
        return VGroup()
    
    n = len(values)
    bar_width = (width / n) * 0.8
    spacing = (width / n) * 0.2
    max_val = max(values) or 1.0
    
    bars = VGroup()
    label_objs = VGroup()
    
    for i, val in enumerate(values):
        h = (val / max_val) * max_height
        bar = Rectangle(width=bar_width, height=h, fill_opacity=0.8, fill_color=color, stroke_width=1)
        bar.move_to(ORIGIN + RIGHT * (i * (bar_width + spacing)) + UP * (h / 2))
        bars.add(bar)
        
        if labels and i < len(labels):
            lbl = Text(labels[i], font_size=20).next_to(bar, DOWN, buff=0.2)
            label_objs.add(lbl)
            
    group = VGroup(bars, label_objs)
    group.center()
    return group


def get_geometric_diagram(
    shape_type: str = "triangle",
    size: float = 2.0,
    color: str = WHITE,
    label: str | None = None,
) -> VGroup:
    """Basic geometric shapes with optional center label."""
    from manim import Circle, Square, Triangle
    
    if shape_type.lower() == "circle":
        mobj = Circle(radius=size/2, color=color)
    elif shape_type.lower() == "square":
        mobj = Square(side_length=size, color=color)
    else:
        mobj = Triangle(color=color).scale(size/1.5)
        
    res = VGroup(mobj)
    if label:
        lbl = Text(label, font_size=24).move_to(mobj.get_center())
        res.add(lbl)
    return res


def dynamic_pointer(target: Mobject, label: str = "Note", direction: Sequence[float] = UP) -> VGroup:
    """Arrow pointing at a target mobject with a label."""
    arrow = Arrow(target.get_center() + direction * 1.5, target.get_center() + direction * 0.2, buff=0)
    lbl = Text(label, font_size=24).next_to(arrow.get_start(), direction, buff=0.1)
    return VGroup(arrow, lbl)


def get_matrix_block(
    matrix_data: Sequence[Sequence[str | float | int]],
    color: str = WHITE,
    cell_font_size: float = 28.0,
) -> VGroup:
    """A 2D grid of elements with manually drawn square brackets (no-LaTeX fallback)."""
    rows = []
    for r in matrix_data:
        # Create a row using get_array_block logic but simplified
        cells = [Text(str(v), font_size=cell_font_size, color=color) for v in r]
        row_group = VGroup(*cells).arrange(RIGHT, buff=0.6)
        rows.append(row_group)
    
    grid = VGroup(*rows).arrange(DOWN, buff=0.6)
    
    # Manual brackets
    h = grid.get_height() + 0.5
    w = 0.2
    
    l_bracket = VGroup(
        Line(UP * h/2 + RIGHT * w, UP * h/2, color=color),
        Line(UP * h/2, DOWN * h/2, color=color),
        Line(DOWN * h/2, DOWN * h/2 + RIGHT * w, color=color)
    ).next_to(grid, LEFT, buff=0.2)
    
    r_bracket = l_bracket.copy().flip(RIGHT).next_to(grid, RIGHT, buff=0.2)
    
    return VGroup(grid, l_bracket, r_bracket)
