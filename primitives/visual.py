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
    NumberPlane,
    Vector,
)
from manim.mobject.mobject import Mobject
from primitives.theme import COLOR_3B1B_BLUE, COLOR_3B1B_YELLOW

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


def get_code_box(code_string: str, language: str = "python") -> Mobject:
    """Syntax-highlighted code block with fallback for missing fonts/dependencies."""
    from manim import BLACK, RoundedRectangle
    try:
        return Code(
            code_string=code_string,
            language=language,
            add_line_numbers=False,
            style="monokai"
        )
    except Exception:
        # Fallback: Dark background + Text
        bg = RoundedRectangle(corner_radius=0.1, fill_color=BLACK, fill_opacity=0.8, stroke_width=1)
        txt = Text(code_string, font="Monospace", font_size=20)
        bg.stretch_to_fit_width(txt.width + 0.5)
        bg.stretch_to_fit_height(txt.height + 0.5)
        return VGroup(bg, txt)


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
    """Equation rendering: `MathTex` when LaTeX is installed, otherwise `Text` fallback.
    
    NOTE: The AI system prompt currently specifies LaTeX is NOT installed. 
    This primitive provides a safe fallback using Text mobjects.
    """
    import shutil

    from manim import ITALIC, MathTex

    # We only use MathTex if explicitly available, otherwise fallback to Text
    if shutil.which("latex") is not None and shutil.which("dvips") is not None:
        try:
            return MathTex(str(latex))
        except Exception:
            # Fallback on render error
            pass
            
    # Fallback: Use Text with a math-like slant
    return Text(str(latex), font_size=36, slant=ITALIC)


def get_labeled_arrow(label: str, buff: float = 0.15) -> VGroup:
    """Arrow from LEFT to RIGHT with a text label above the shaft."""
    arrow = Arrow(LEFT * 2.2, RIGHT * 2.2, buff=0.05)
    lbl = Text(str(label), font_size=28).next_to(arrow, UP, buff=buff)
    return VGroup(arrow, lbl)


def get_number_line(
    x_range: Sequence[float],
    length: float = 8.0,
    include_numbers: bool = False,
) -> NumberLine:
    """Number line with tick spacing from `x_range` (start, end, step).
    
    Defaults to `include_numbers=False` as LaTeX is often unavailable in CI.
    """
    import shutil
    if len(x_range) < 3:
        # Prevent crash on malformed input
        start, end, step = (x_range[0], x_range[1], 1.0) if len(x_range) == 2 else (0, 10, 1)
    else:
        start, end, step = x_range[:3]
        
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


def dynamic_pointer(target: Mobject, label: str = "Note", direction: str | Sequence[float] | None = None) -> VGroup:
    """Arrow pointing at a target mobject with a label. Handles string directions."""
    import numpy as np
    
    # Map string directions to Manim vectors
    dir_map = {"UP": UP, "DOWN": DOWN, "LEFT": LEFT, "RIGHT": RIGHT}
    if isinstance(direction, str):
        dir_vec = dir_map.get(direction.upper(), UP)
    elif direction is not None:
        dir_vec = np.array(direction)
    else:
        dir_vec = UP
    
    arrow = Arrow(target.get_center() + dir_vec * 1.5, target.get_center() + dir_vec * 0.2, buff=0)
    lbl = Text(label, font_size=24).next_to(arrow.get_start(), dir_vec, buff=0.1)
    return VGroup(arrow, lbl)


def get_math_grid(
    x_range: Sequence[float] = (-8, 8, 1),
    y_range: Sequence[float] = (-5, 5, 1),
) -> NumberPlane:
    """3B1B-style NumberPlane with subtle grid lines."""
    return NumberPlane(
        x_range=x_range,
        y_range=y_range,
        background_line_style={
            "stroke_color": COLOR_3B1B_BLUE,
            "stroke_width": 1,
            "stroke_opacity": 0.1,
        },
        axis_config={"stroke_color": WHITE, "stroke_width": 2},
    )


def get_vector_arrow(coords: Sequence[float], label: str | None = None, color: str = COLOR_3B1B_YELLOW) -> VGroup:
    """Vector arrow with optional label at the tip."""
    import numpy as np
    vec = Vector(coords, color=color)
    res = VGroup(vec)
    if label:
        lbl = Text(f"({coords[0]}, {coords[1]})" if label == "auto" else label, font_size=20, color=color)
        lbl.next_to(vec.get_end(), vec.get_vector(), buff=0.2)
        res.add(lbl)
    return res


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
