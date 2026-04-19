from __future__ import annotations

from collections.abc import Callable

import pytest

pytest.importorskip("manim", reason="Manim is required for primitive smoke tests")

import primitives as prim
from manim import Text


def _t(label: str = "x") -> Text:
    return Text(label, font_size=20)


_BUILDERS: list[tuple[str, Callable[[], object]]] = [
    ("get_text_panel", lambda: prim.get_text_panel("hi")),
    ("get_array_block", lambda: prim.get_array_block([1, 2, 3])),
    ("get_code_box", lambda: prim.get_code_box("print(1)\n", language="python")),
    ("get_title_card", lambda: prim.get_title_card("Title", subtitle="Sub")),
    ("get_bulleted_list", lambda: prim.get_bulleted_list(["a", "b"])),
    ("get_equation_block", lambda: prim.get_equation_block(r"x=1")),
    ("get_labeled_arrow", lambda: prim.get_labeled_arrow("label")),
    ("get_number_line", lambda: prim.get_number_line((-2, 2, 1), length=6.0)),
    ("get_separator_line", lambda: prim.get_separator_line(width=4.0)),
    ("cinematic_fade_in", lambda: prim.cinematic_fade_in(_t("a"), duration=0.1)),
    ("cinematic_fade_out", lambda: prim.cinematic_fade_out(_t("b"), duration=0.1)),
    (
        "smooth_transform",
        lambda: prim.smooth_transform(_t("from"), _t("to"), duration=0.1),
    ),
    ("focus_highlight", lambda: prim.focus_highlight(_t("c"))),
    ("write_on", lambda: prim.write_on(_t("d"), run_time=0.2)),
    ("flash_attention", lambda: prim.flash_attention(_t("e"))),
    ("surround_pulse", lambda: prim.surround_pulse(_t("f"))),
    ("stack_horizontal", lambda: prim.stack_horizontal(_t("1"), _t("2"))),
    ("stack_vertical", lambda: prim.stack_vertical(_t("1"), _t("2"))),
    ("center_mobject", lambda: prim.center_mobject(_t("g"))),
    ("surround_with_frame", lambda: prim.surround_with_frame(_t("h"))),
    ("scale_to_width", lambda: prim.scale_to_width(_t("i"), width=3.0)),
]


@pytest.mark.parametrize("name,builder", _BUILDERS, ids=[n for n, _ in _BUILDERS])
def test_public_primitive_smoke(name: str, builder: Callable[[], object]) -> None:
    _ = name
    built = builder()
    assert built is not None
