from __future__ import annotations

from collections.abc import Callable
from typing import Any

from shared.schemas.primitives_catalog import (
    PrimitiveEntry,
    PrimitiveKind,
    PrimitiveParameter,
    PrimitivesCatalogResponse,
)

from primitives.constants import CATALOG_VERSION

_PRIMITIVES: list[PrimitiveEntry] = []


def _p(
    name: str,
    kind: PrimitiveKind,
    *,
    required: bool = True,
    default: str | None = None,
    description: str | None = None,
) -> PrimitiveParameter:
    return PrimitiveParameter(
        name=name,
        kind=kind,
        required=required,
        default=default,
        description=description,
    )


def _e(
    *,
    name: str,
    module: str,
    description: str,
    parameters: list[PrimitiveParameter],
    example: str,
    tags: list[str] | None = None,
) -> PrimitiveEntry:
    return PrimitiveEntry(
        name=name,
        module=module,
        description=description,
        parameters=parameters,
        example=example,
        tags=tags or [],
    )


def register_primitive(
    *,
    name: str,
    module: str,
    description: str,
    parameters: list[PrimitiveParameter],
    example: str,
    tags: list[str] | None = None,
) -> Callable[[Any], Any]:
    """Decorator to register a primitive function."""

    def decorator(func: Any) -> Any:
        entry = _e(
            name=name,
            module=module,
            description=description,
            parameters=parameters,
            example=example,
            tags=tags,
        )
        _PRIMITIVES.append(entry)
        return func

    return decorator


def build_primitives_catalog() -> PrimitivesCatalogResponse:
    return PrimitivesCatalogResponse(version=CATALOG_VERSION, primitives=_PRIMITIVES)


def catalog_primitive_names() -> set[str]:
    return {p.name for p in _PRIMITIVES}


# --- Register Initial Primitives ---
# (Usually these would be above the actual function definitions in primitives/*.py)
# For now, we maintain the catalog here for backward compatibility but using the registry pattern.

_STATIC_PRIMITIVES = [
    # Visual
    _e(
        name="get_text_panel",
        module="primitives.visual",
        description="Create consistent body/title text.",
        parameters=[
            _p("text", "str"),
            _p("color", "str", required=False, default="BLUE"),
            _p("font_size", "float", required=False, default="40"),
        ],
        example='get_text_panel("Binary Search", color=BLUE, font_size=44)',
        tags=["visual", "text"],
    ),
    _e(
        name="get_array_block",
        module="primitives.visual",
        description="Render values as a horizontal row with optional highlight.",
        parameters=[
            _p("values", "list"),
            _p("highlight_index", "int", required=False, default="0"),
            _p("cell_font_size", "float", required=False, default="32"),
        ],
        example="get_array_block([1, 2, 3, 4], highlight_index=1)",
        tags=["visual", "array"],
    ),
    _e(
        name="get_code_box",
        module="primitives.visual",
        description="Syntax-highlighted code block with Monokai theme.",
        parameters=[
            _p("code_string", "str"),
            _p("language", "str", required=False, default="python"),
        ],
        example='get_code_box("def f(x):\\n    return x*x", language="python")',
        tags=["visual", "code"],
    ),
    _e(
        name="get_title_card",
        module="primitives.visual",
        description="Title with optional subtitle stacked vertically.",
        parameters=[_p("title", "str"), _p("subtitle", "str", required=False, default=None)],
        example='get_title_card("Topic", subtitle="Part 1")',
        tags=["visual", "text"],
    ),
    _e(
        name="get_bulleted_list",
        module="primitives.visual",
        description="Bulleted list (text-based; no LaTeX toolchain required).",
        parameters=[_p("items", "list")],
        example='get_bulleted_list(["Step 1", "Step 2"])',
        tags=["visual", "text"],
    ),
    _e(
        name="get_equation_block",
        module="primitives.visual",
        description="Equation block: Automatically falls back to standard Text.",
        parameters=[_p("latex", "str")],
        example=r'get_equation_block(r"\\int_0^1 x\\,dx")',
        tags=["visual", "math"],
    ),
    _e(
        name="get_labeled_arrow",
        module="primitives.visual",
        description="Arrow with a label above the shaft.",
        parameters=[_p("label", "str"), _p("buff", "float", required=False, default="0.15")],
        example='get_labeled_arrow("increases")',
        tags=["visual", "diagram"],
    ),
    _e(
        name="get_number_line",
        module="primitives.visual",
        description="NumberLine with tick spacing.",
        parameters=[
            _p("x_range", "object"),
            _p("length", "float", required=False, default="8"),
            _p("include_numbers", "bool", required=False, default="false"),
        ],
        example="get_number_line((-3, 3, 1), length=10, include_numbers=True)",
        tags=["visual", "math"],
    ),
    _e(
        name="get_separator_line",
        module="primitives.visual",
        description="Horizontal separator line.",
        parameters=[
            _p("width", "float", required=False, default="10"),
            _p("color", "str", required=False, default="WHITE"),
        ],
        example="get_separator_line(width=12)",
        tags=["visual", "layout"],
    ),
    # Animations
    _e(
        name="cinematic_fade_in",
        module="primitives.animation",
        description="Fade-in animation with explicit run time.",
        parameters=[
            _p("mobject", "mobject"),
            _p("duration", "float", required=False, default="0.75"),
        ],
        example="self.play(cinematic_fade_in(title, duration=0.8))",
        tags=["animation"],
    ),
    _e(
        name="cinematic_fade_out",
        module="primitives.animation",
        description="Fade-out animation with explicit run time.",
        parameters=[
            _p("mobject", "mobject"),
            _p("duration", "float", required=False, default="0.75"),
        ],
        example="self.play(cinematic_fade_out(title))",
        tags=["animation"],
    ),
    _e(
        name="cinematic_entrance",
        module="primitives.animation",
        description="3B1B-style entrance: FadeIn + Shift UP.",
        parameters=[
            _p("mobject", "mobject"),
            _p("duration", "float", required=False, default="0.8"),
        ],
        example="self.play(cinematic_entrance(title))",
        tags=["animation"],
    ),
    _e(
        name="cascade_fade_out",
        module="primitives.animation",
        description="Staggered exit.",
        parameters=[_p("scene", "scene"), _p("group", "list")],
        example="cascade_fade_out(self, items)",
        tags=["animation"],
    ),
    _e(
        name="smooth_transform",
        module="primitives.animation",
        description="Transform one mobject into another.",
        parameters=[
            _p("mobject_from", "mobject"),
            _p("mobject_to", "mobject"),
            _p("duration", "float", required=False, default="0.9"),
        ],
        example="self.play(smooth_transform(a, b))",
        tags=["animation"],
    ),
    _e(
        name="focus_highlight",
        module="primitives.animation",
        description="Indicate/highlight a mobject briefly.",
        parameters=[
            _p("mobject", "mobject"),
            _p("scale_factor", "float", required=False, default="1.08"),
        ],
        example="self.play(focus_highlight(box))",
        tags=["animation"],
    ),
    _e(
        name="write_on",
        module="primitives.animation",
        description="Write animation for text-like mobjects.",
        parameters=[
            _p("mobject", "mobject"),
            _p("run_time", "float", required=False, default="1.0"),
        ],
        example="self.play(write_on(caption))",
        tags=["animation"],
    ),
    _e(
        name="flash_attention",
        module="primitives.animation",
        description="Short flash burst around a mobject.",
        parameters=[
            _p("mobject", "mobject"),
            _p("line_length", "float", required=False, default="0.2"),
            _p("num_lines", "int", required=False, default="12"),
        ],
        example="self.play(flash_attention(dot))",
        tags=["animation"],
    ),
    _e(
        name="surround_pulse",
        module="primitives.animation",
        description="Circumscribe emphasis around a mobject.",
        parameters=[_p("mobject", "mobject"), _p("color", "str", required=False, default=None)],
        example="self.play(surround_pulse(group, color=YELLOW))",
        tags=["animation"],
    ),
    # Layout
    _e(
        name="stack_horizontal",
        module="primitives.layout",
        description="Pack mobjects in a row.",
        parameters=[_p("mobjects", "object"), _p("buff", "float", required=False, default="0.35")],
        example="stack_horizontal(a, b, c, buff=0.5)",
        tags=["layout"],
    ),
    _e(
        name="stack_vertical",
        module="primitives.layout",
        description="Pack mobjects in a column.",
        parameters=[_p("mobjects", "object"), _p("buff", "float", required=False, default="0.35")],
        example="stack_vertical(title, body, buff=0.4)",
        tags=["layout"],
    ),
    _e(
        name="center_mobject",
        module="primitives.layout",
        description="Center a mobject about the origin.",
        parameters=[_p("mobject", "mobject")],
        example="center_mobject(title)",
        tags=["layout"],
    ),
    _e(
        name="surround_with_frame",
        module="primitives.layout",
        description="SurroundingRectangle frame around a mobject.",
        parameters=[
            _p("mobject", "mobject"),
            _p("buff", "float", required=False, default="SMALL_BUFF"),
            _p("color", "str", required=False, default="WHITE"),
        ],
        example="surround_with_frame(panel, buff=0.2)",
        tags=["layout"],
    ),
    _e(
        name="scale_to_width",
        module="primitives.layout",
        description="Uniformly scale a mobject to a target width.",
        parameters=[_p("mobject", "mobject"), _p("width", "float")],
        example="scale_to_width(figure, width=10)",
        tags=["layout"],
    ),
    # More Visual/Pedagogy
    _e(
        name="get_data_chart",
        module="primitives.visual",
        description="Simple bar chart using rectangles.",
        parameters=[_p("values", "list"), _p("labels", "list", required=False, default=None)],
        example='get_data_chart([10, 20, 30], labels=["A", "B", "C"])',
        tags=["visual", "math", "chart"],
    ),
    _e(
        name="get_geometric_diagram",
        module="primitives.visual",
        description="Basic geometric shapes.",
        parameters=[_p("shape_type", "str", required=False, default="triangle")],
        example='get_geometric_diagram("circle", size=3, label="Core")',
        tags=["visual", "geometry"],
    ),
    _e(
        name="dynamic_pointer",
        module="primitives.visual",
        description="Arrow pointing at a target mobject.",
        parameters=[_p("target", "mobject"), _p("label", "str", required=False, default="Note")],
        example="dynamic_pointer(box, label='Highlight')",
        tags=["visual", "diagram"],
    ),
    _e(
        name="highlight_region",
        module="primitives.animation",
        description="Returns a Cutout dimmer.",
        parameters=[_p("mobject", "mobject")],
        example="dimmer = highlight_region(box)",
        tags=["animation", "focus"],
    ),
    _e(
        name="get_matrix_block",
        module="primitives.visual",
        description="A 2D grid of elements.",
        parameters=[_p("matrix_data", "list")],
        example="get_matrix_block([[1, 0], [0, 1]])",
        tags=["visual", "math", "matrix"],
    ),
    _e(
        name="get_math_grid",
        module="primitives.visual",
        description="3B1B-style NumberPlane.",
        parameters=[_p("x_range", "list", required=False, default="(-8, 8, 1)")],
        example="get_math_grid()",
        tags=["visual", "math", "grid"],
    ),
    _e(
        name="get_vector_arrow",
        module="primitives.visual",
        description="Vector arrow with coordinate label.",
        parameters=[_p("coords", "list")],
        example="get_vector_arrow([2, 3])",
        tags=["visual", "math", "vector"],
    ),
    _e(
        name="get_info_box",
        module="primitives.visual",
        description="Styled information box.",
        parameters=[_p("text", "str")],
        example='get_info_box("Note", color=YELLOW)',
        tags=["visual", "layout"],
    ),
    _e(
        name="get_two_column",
        module="primitives.visual",
        description="Side-by-side layout.",
        parameters=[_p("left_mobj", "mobject"), _p("right_mobj", "mobject")],
        example="get_two_column(a, b)",
        tags=["visual", "layout"],
    ),
    _e(
        name="get_table_block",
        module="primitives.visual",
        description="Text-based table.",
        parameters=[_p("headers", "list"), _p("rows", "list")],
        example='get_table_block(["A"], [["1"]])',
        tags=["visual", "table"],
    ),
    _e(
        name="get_step_indicator",
        module="primitives.visual",
        description="Progress dots indicator.",
        parameters=[_p("total", "int"), _p("current", "int")],
        example="get_step_indicator(5, 2)",
        tags=["visual", "indicator"],
    ),
    _e(
        name="get_key_value_panel",
        module="primitives.visual",
        description="Vertical list of Key: Value pairs.",
        parameters=[_p("pairs", "list")],
        example='get_key_value_panel([("T", "1")])',
        tags=["visual", "text"],
    ),
    # Pedagogy
    _e(
        name="equation_morph",
        module="primitives.pedagogy",
        description="Smooth transformation between two math strings.",
        parameters=[_p("scene", "scene"), _p("text_from", "str"), _p("text_to", "str")],
        example='equation_morph(self, "a", "b")',
        tags=["pedagogy", "animation"],
    ),
    _e(
        name="progressive_reveal",
        module="primitives.pedagogy",
        description="Staggered entrance of mobjects.",
        parameters=[_p("scene", "scene"), _p("group", "list")],
        example="progressive_reveal(self, [m1, m2])",
        tags=["pedagogy", "animation"],
    ),
    _e(
        name="progressive_remove",
        module="primitives.pedagogy",
        description="Staggered exit of mobjects.",
        parameters=[_p("scene", "scene"), _p("group", "list")],
        example="progressive_remove(self, [m1, m2])",
        tags=["pedagogy", "animation"],
    ),
    _e(
        name="counter_animate",
        module="primitives.pedagogy",
        description="Animated counting number.",
        parameters=[_p("scene", "scene"), _p("start_val", "float"), _p("end_val", "float")],
        example="counter_animate(self, 0, 100)",
        tags=["pedagogy", "animation"],
    ),
    _e(
        name="theorem_reveal",
        module="primitives.pedagogy",
        description="Reveal theorem then sequential proof steps.",
        parameters=[_p("scene", "scene"), _p("statement", "str"), _p("proof_steps", "list")],
        example='theorem_reveal(self, "T", [s1])',
        tags=["pedagogy", "animation"],
    ),
    _e(
        name="graph_trace",
        module="primitives.pedagogy",
        description="Progressively draw a function.",
        parameters=[
            _p("scene", "scene"),
            _p("axes", "mobject"),
            _p("func", "object"),
            _p("x_range", "list"),
        ],
        example="graph_trace(self, axes, f, [0, 1])",
        tags=["pedagogy", "animation"],
    ),
    _e(
        name="notation_swap",
        module="primitives.pedagogy",
        description="Smooth replacement (cross-fade).",
        parameters=[_p("scene", "scene"), _p("mob_from", "mobject"), _p("mob_to", "mobject")],
        example="notation_swap(self, a, b)",
        tags=["pedagogy", "animation"],
    ),
    # Animation V2
    _e(
        name="cascade_fade_in",
        module="primitives.animation",
        description="Staggered entrance.",
        parameters=[_p("scene", "scene"), _p("group", "list")],
        example="cascade_fade_in(self, items)",
        tags=["animation"],
    ),
    _e(
        name="focus_zoom",
        module="primitives.animation",
        description="Camera zoom.",
        parameters=[_p("scene", "scene"), _p("target", "mobject")],
        example="focus_zoom(self, p)",
        tags=["animation", "focus"],
    ),
    _e(
        name="sweep_reveal",
        module="primitives.animation",
        description="Reveal with shift.",
        parameters=[_p("scene", "scene"), _p("mobject", "mobject")],
        example="sweep_reveal(self, t)",
        tags=["animation"],
    ),
    _e(
        name="typewriter_text",
        module="primitives.animation",
        description="Typewriter effect.",
        parameters=[_p("scene", "scene"), _p("text", "object")],
        example="typewriter_text(self, t)",
        tags=["animation", "text"],
    ),
    _e(
        name="wave_emphasis",
        module="primitives.animation",
        description="Wave emphasis.",
        parameters=[_p("scene", "scene"), _p("target", "mobject")],
        example="wave_emphasis(self, t)",
        tags=["animation"],
    ),
    # Domain
    _e(
        name="get_graph_network",
        module="primitives.domain",
        description="Graph visualization.",
        parameters=[_p("vertices", "list"), _p("edges", "list")],
        example="get_graph_network([1], [])",
        tags=["domain", "graph"],
    ),
    _e(
        name="get_binary_tree",
        module="primitives.domain",
        description="Binary tree visualization.",
        parameters=[_p("values", "list")],
        example="get_binary_tree([1])",
        tags=["domain", "tree"],
    ),
    _e(
        name="get_timeline",
        module="primitives.domain",
        description="Horizontal timeline.",
        parameters=[_p("events", "list")],
        example="get_timeline([])",
        tags=["domain", "timeline"],
    ),
    _e(
        name="get_flowchart",
        module="primitives.domain",
        description="Vertical flowchart.",
        parameters=[_p("steps", "list")],
        example="get_flowchart([])",
        tags=["domain", "flowchart"],
    ),
]

_PRIMITIVES.extend(_STATIC_PRIMITIVES)
