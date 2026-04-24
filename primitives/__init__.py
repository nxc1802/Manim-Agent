"""Manim helper primitives for the Builder (lazy imports — no Manim until used)."""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "CATALOG_VERSION",
    "cinematic_fade_in",
    "cinematic_fade_out",
    "cinematic_entrance",
    "center_mobject",
    "dynamic_pointer",
    "flash_attention",
    "focus_highlight",
    "get_array_block",
    "get_bulleted_list",
    "get_code_box",
    "get_data_chart",
    "get_equation_block",
    "get_geometric_diagram",
    "get_labeled_arrow",
    "get_math_grid",
    "get_matrix_block",
    "get_number_line",
    "get_separator_line",
    "get_text_panel",
    "get_title_card",
    "get_vector_arrow",
    "highlight_region",
    "scale_to_width",
    "smooth_transform",
    "stack_horizontal",
    "stack_vertical",
    "surround_pulse",
    "surround_with_frame",
    "write_on",
]

_EXPORTS: dict[str, tuple[str, str]] = {
    "cinematic_fade_in": ("primitives.animation", "cinematic_fade_in"),
    "cinematic_fade_out": ("primitives.animation", "cinematic_fade_out"),
    "cinematic_entrance": ("primitives.animation", "cinematic_entrance"),
    "flash_attention": ("primitives.animation", "flash_attention"),
    "focus_highlight": ("primitives.animation", "focus_highlight"),
    "highlight_region": ("primitives.animation", "highlight_region"),
    "smooth_transform": ("primitives.animation", "smooth_transform"),
    "surround_pulse": ("primitives.animation", "surround_pulse"),
    "write_on": ("primitives.animation", "write_on"),
    "center_mobject": ("primitives.layout", "center_mobject"),
    "scale_to_width": ("primitives.layout", "scale_to_width"),
    "stack_horizontal": ("primitives.layout", "stack_horizontal"),
    "stack_vertical": ("primitives.layout", "stack_vertical"),
    "surround_with_frame": ("primitives.layout", "surround_with_frame"),
    "dynamic_pointer": ("primitives.visual", "dynamic_pointer"),
    "get_array_block": ("primitives.visual", "get_array_block"),
    "get_bulleted_list": ("primitives.visual", "get_bulleted_list"),
    "get_code_box": ("primitives.visual", "get_code_box"),
    "get_data_chart": ("primitives.visual", "get_data_chart"),
    "get_equation_block": ("primitives.visual", "get_equation_block"),
    "get_geometric_diagram": ("primitives.visual", "get_geometric_diagram"),
    "get_labeled_arrow": ("primitives.visual", "get_labeled_arrow"),
    "get_math_grid": ("primitives.visual", "get_math_grid"),
    "get_matrix_block": ("primitives.visual", "get_matrix_block"),
    "get_number_line": ("primitives.visual", "get_number_line"),
    "get_separator_line": ("primitives.visual", "get_separator_line"),
    "get_text_panel": ("primitives.visual", "get_text_panel"),
    "get_title_card": ("primitives.visual", "get_title_card"),
    "get_vector_arrow": ("primitives.visual", "get_vector_arrow"),
}


def __getattr__(name: str) -> Any:
    if name == "CATALOG_VERSION":
        from primitives.constants import CATALOG_VERSION as value

        return value

    location = _EXPORTS.get(name)
    if location is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr = location
    module = importlib.import_module(module_name)
    value = getattr(module, attr)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(__all__) | set(globals().keys()))
