from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from manim import BLUE, DOWN, LEFT, RIGHT, UP, WHITE, VGroup


def get_graph_network(
    vertices: Sequence[Any],
    edges: Sequence[tuple[Any, Any]],
    layout: str = "spring",
    vertex_color: str = BLUE,
    edge_color: str = WHITE,
) -> VGroup:
    """Graph/Network visualization using Manim's Graph class."""
    from manim import Graph

    return Graph(
        vertices,
        edges,
        layout=layout,
        vertex_config={"fill_color": vertex_color},
        edge_config={"stroke_color": edge_color},
    )


def get_binary_tree(
    values: Sequence[Any],
    highlight_path: Sequence[int] | None = None,
    level_height: float = 1.5,
    sibling_width: float = 3.0,
) -> VGroup:
    """Simple binary tree visualization."""
    from manim import BLUE, WHITE, Circle, Line, Text

    mobjs = VGroup()
    if not values:
        return mobjs

    def build_tree(idx: int, pos: Any, width: float) -> VGroup:
        if idx >= len(values) or values[idx] is None:
            return VGroup()

        node_val = Text(str(values[idx]), font_size=24)
        node_circ = Circle(radius=0.4, color=WHITE).move_to(pos)
        if highlight_path and idx in highlight_path:
            node_circ.set_color(BLUE)

        node = VGroup(node_circ, node_val)
        mobjs.add(node)

        # Left child
        left_idx = 2 * idx + 1
        if left_idx < len(values) and values[left_idx] is not None:
            left_pos = pos + DOWN * level_height + LEFT * width / 2
            line = Line(node_circ.get_bottom(), left_pos + UP * 0.4, stroke_width=2)
            mobjs.add(line)
            build_tree(left_idx, left_pos, width / 2)

        # Right child
        right_idx = 2 * idx + 2
        if right_idx < len(values) and values[right_idx] is not None:
            right_pos = pos + DOWN * level_height + RIGHT * width / 2
            line = Line(node_circ.get_bottom(), right_pos + UP * 0.4, stroke_width=2)
            mobjs.add(line)
            build_tree(right_idx, right_pos, width / 2)

        return node

    build_tree(0, UP * 2, sibling_width)
    return mobjs


def get_timeline(
    events: Sequence[tuple[float, str]], length: float = 10.0, color: str = WHITE
) -> VGroup:
    """Horizontal timeline with labeled events."""
    from manim import DOWN, UP, Dot, NumberLine, Text

    if not events:
        return VGroup()

    times = [e[0] for e in events]
    t_min, t_max = min(times), max(times)
    if t_min == t_max:
        t_max += 1.0

    line = NumberLine(x_range=[t_min, t_max, (t_max - t_min) / 10], length=length, color=color)
    res = VGroup(line)

    for i, (t, label) in enumerate(events):
        p = line.n2p(t)
        dot = Dot(p, color=BLUE)
        lbl = Text(label, font_size=20).next_to(dot, UP if i % 2 == 0 else DOWN, buff=0.3)
        res.add(dot, lbl)

    return res


def get_flowchart(
    steps: Sequence[str], connections: Sequence[tuple[int, int]] | None = None
) -> VGroup:
    """Simple vertical flowchart."""
    from manim import DOWN, Arrow, RoundedRectangle, Text

    boxes = VGroup()
    for s in steps:
        txt = Text(s, font_size=24)
        box = RoundedRectangle(corner_radius=0.1, width=txt.width + 0.5, height=txt.height + 0.5)
        boxes.add(VGroup(box, txt))

    boxes.arrange(DOWN, buff=1.0)
    res = VGroup(boxes)

    if connections:
        for i, j in connections:
            start = boxes[i].get_bottom()
            end = boxes[j].get_top()
            res.add(Arrow(start, end, buff=0.1))
    else:
        # Default: linear connection
        for i in range(len(boxes) - 1):
            res.add(Arrow(boxes[i].get_bottom(), boxes[i + 1].get_top(), buff=0.1))

    return res
