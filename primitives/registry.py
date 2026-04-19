from __future__ import annotations

from shared.schemas.primitives_catalog import (
    PrimitiveEntry,
    PrimitiveKind,
    PrimitiveParameter,
    PrimitivesCatalogResponse,
)

from primitives.constants import CATALOG_VERSION


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


_PRIMITIVES: list[PrimitiveEntry] = [
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
        description="Syntax-highlighted code block.",
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
        parameters=[
            _p("title", "str"),
            _p("subtitle", "str", required=False, default=None),
        ],
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
        description="Equation: uses MathTex when `latex` exists, otherwise Text fallback.",
        parameters=[_p("latex", "str")],
        example=r'get_equation_block(r"\\int_0^1 x\\,dx")',
        tags=["visual", "math"],
    ),
    _e(
        name="get_labeled_arrow",
        module="primitives.visual",
        description="Arrow with a label above the shaft.",
        parameters=[
            _p("label", "str"),
            _p("buff", "float", required=False, default="0.15"),
        ],
        example='get_labeled_arrow("increases")',
        tags=["visual", "diagram"],
    ),
    _e(
        name="get_number_line",
        module="primitives.visual",
        description="NumberLine with tick spacing; numbers off by default (LaTeX if enabled).",
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
        parameters=[
            _p("mobject", "mobject"),
            _p("color", "str", required=False, default=None),
        ],
        example="self.play(surround_pulse(group, color=YELLOW))",
        tags=["animation"],
    ),
    _e(
        name="stack_horizontal",
        module="primitives.layout",
        description="Pack mobjects in a row.",
        parameters=[
            _p("mobjects", "object"),
            _p("buff", "float", required=False, default="0.35"),
        ],
        example="stack_horizontal(a, b, c, buff=0.5)",
        tags=["layout"],
    ),
    _e(
        name="stack_vertical",
        module="primitives.layout",
        description="Pack mobjects in a column.",
        parameters=[
            _p("mobjects", "object"),
            _p("buff", "float", required=False, default="0.35"),
        ],
        example="stack_vertical(title, body, buff=0.4)",
        tags=["layout"],
    ),
    _e(
        name="center_mobject",
        module="primitives.layout",
        description="Center a mobject about the origin (mutates).",
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
        description="Uniformly scale a mobject to a target width (mutates).",
        parameters=[
            _p("mobject", "mobject"),
            _p("width", "float"),
        ],
        example="scale_to_width(figure, width=10)",
        tags=["layout"],
    ),
]


def build_primitives_catalog() -> PrimitivesCatalogResponse:
    return PrimitivesCatalogResponse(version=CATALOG_VERSION, primitives=_PRIMITIVES)


def catalog_primitive_names() -> set[str]:
    return {p.name for p in _PRIMITIVES}
