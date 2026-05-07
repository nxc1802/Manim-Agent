"""Manim helper primitives for the Builder (lazy imports — no Manim until used)."""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "CATALOG_VERSION",
    # Animation
    "cinematic_fade_in",
    "cinematic_fade_out",
    "cinematic_entrance",
    "flash_attention",
    "focus_highlight",
    "highlight_region",
    "smooth_transform",
    "surround_pulse",
    "write_on",
    "cascade_fade_in",
    "cascade_fade_out",
    "focus_zoom",
    "sweep_reveal",
    "typewriter_text",
    "wave_emphasis",
    # Layout
    "center_mobject",
    "scale_to_width",
    "stack_horizontal",
    "stack_vertical",
    "surround_with_frame",
    # Visual
    "dynamic_pointer",
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
    "get_info_box",
    "get_two_column",
    "get_table_block",
    "get_step_indicator",
    "get_key_value_panel",
    # Pedagogy
    "equation_morph",
    "progressive_reveal",
    "progressive_remove",
    "counter_animate",
    "theorem_reveal",
    "graph_trace",
    "notation_swap",
    # Domain
    "get_graph_network",
    "get_binary_tree",
    "get_timeline",
    "get_flowchart",
]

_EXPORTS: dict[str, tuple[str, str]] = {
    # animation.py
    "cinematic_fade_in": ("primitives.animation", "cinematic_fade_in"),
    "cinematic_fade_out": ("primitives.animation", "cinematic_fade_out"),
    "cinematic_entrance": ("primitives.animation", "cinematic_entrance"),
    "flash_attention": ("primitives.animation", "flash_attention"),
    "focus_highlight": ("primitives.animation", "focus_highlight"),
    "highlight_region": ("primitives.animation", "highlight_region"),
    "smooth_transform": ("primitives.animation", "smooth_transform"),
    "surround_pulse": ("primitives.animation", "surround_pulse"),
    "write_on": ("primitives.animation", "write_on"),
    "cascade_fade_in": ("primitives.animation", "cascade_fade_in"),
    "cascade_fade_out": ("primitives.animation", "cascade_fade_out"),
    "focus_zoom": ("primitives.animation", "focus_zoom"),
    "sweep_reveal": ("primitives.animation", "sweep_reveal"),
    "typewriter_text": ("primitives.animation", "typewriter_text"),
    "wave_emphasis": ("primitives.animation", "wave_emphasis"),
    # layout.py
    "center_mobject": ("primitives.layout", "center_mobject"),
    "scale_to_width": ("primitives.layout", "scale_to_width"),
    "stack_horizontal": ("primitives.layout", "stack_horizontal"),
    "stack_vertical": ("primitives.layout", "stack_vertical"),
    "surround_with_frame": ("primitives.layout", "surround_with_frame"),
    # visual.py
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
    "get_info_box": ("primitives.visual", "get_info_box"),
    "get_two_column": ("primitives.visual", "get_two_column"),
    "get_table_block": ("primitives.visual", "get_table_block"),
    "get_step_indicator": ("primitives.visual", "get_step_indicator"),
    "get_key_value_panel": ("primitives.visual", "get_key_value_panel"),
    # pedagogy.py
    "equation_morph": ("primitives.pedagogy", "equation_morph"),
    "progressive_reveal": ("primitives.pedagogy", "progressive_reveal"),
    "progressive_remove": ("primitives.pedagogy", "progressive_remove"),
    "counter_animate": ("primitives.pedagogy", "counter_animate"),
    "theorem_reveal": ("primitives.pedagogy", "theorem_reveal"),
    "graph_trace": ("primitives.pedagogy", "graph_trace"),
    "notation_swap": ("primitives.pedagogy", "notation_swap"),
    # domain.py
    "get_graph_network": ("primitives.domain", "get_graph_network"),
    "get_binary_tree": ("primitives.domain", "get_binary_tree"),
    "get_timeline": ("primitives.domain", "get_timeline"),
    "get_flowchart": ("primitives.domain", "get_flowchart"),
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
