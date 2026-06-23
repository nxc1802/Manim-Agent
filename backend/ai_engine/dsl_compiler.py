from __future__ import annotations

import ast
import logging
import re
from typing import Any

from primitives.registry import build_primitives_catalog
from shared.schemas.scene_dsl import AnimationStep, Position, SceneDSL, SceneDSLBeat, VisualElement

logger = logging.getLogger(__name__)

_DSL_CONSTRUCTORS = {
    cls.__name__: cls
    for cls in (
        AnimationStep,
        Position,
        SceneDSLBeat,
        VisualElement,
    )
}
_DSL_FIELDS = {"title", "beats", "global_theme", "metadata", "version"}
_SAFE_PARAM_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

SCENE_PLAYING_ANIMATIONS = {
    "cascade_fade_in",
    "cascade_fade_out",
    "focus_zoom",
    "sweep_reveal",
    "typewriter_text",
    "wave_emphasis",
}


def format_arg(val: Any) -> str:
    """Helper to convert values to python code representation, keeping Manim constants raw."""
    if isinstance(val, str):
        import manim

        if re.fullmatch(r"[A-Z][A-Z0-9_]*", val) and hasattr(manim, val):
            return val
        return repr(val)
    elif isinstance(val, list):
        return "[" + ", ".join(format_arg(x) for x in val) + "]"
    elif isinstance(val, tuple):
        return "(" + ", ".join(format_arg(x) for x in val) + ")"
    elif isinstance(val, dict):
        return "{" + ", ".join(f"{repr(k)}: {format_arg(v)}" for k, v in val.items()) + "}"
    else:
        return repr(val)


def _dsl_constructors() -> dict[str, type[Any]]:
    from shared.schemas.scene_dsl import (
        CameraState,
        ThemeConfig,
        TransitionSpec,
    )

    return {
        **_DSL_CONSTRUCTORS,
        "CameraState": CameraState,
        "ThemeConfig": ThemeConfig,
        "TransitionSpec": TransitionSpec,
    }


def _evaluate_dsl_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_evaluate_dsl_node(item) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_evaluate_dsl_node(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        if any(key is None for key in node.keys):
            raise ValueError("Dictionary unpacking is not allowed in Scene DSL")
        result: dict[Any, Any] = {}
        for key, value in zip(node.keys, node.values, strict=True):
            assert key is not None
            result[_evaluate_dsl_node(key)] = _evaluate_dsl_node(value)
        return result
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate_dsl_node(node.operand)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("Unary operators are only allowed for numbers")
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        constructor = _dsl_constructors().get(node.func.id)
        if constructor is None:
            raise ValueError(f"Unsupported Scene DSL constructor: {node.func.id}")
        if node.args:
            raise ValueError("Scene DSL constructors require keyword arguments")
        kwargs: dict[str, Any] = {}
        for keyword in node.keywords:
            if keyword.arg is None:
                raise ValueError("Keyword unpacking is not allowed in Scene DSL")
            kwargs[keyword.arg] = _evaluate_dsl_node(keyword.value)
        return constructor(**kwargs)
    raise ValueError(f"Unsupported Scene DSL expression: {type(node).__name__}")


def parse_python_class_dsl(source_code: str) -> SceneDSL:
    """Parse the Python-shaped DSL without executing any submitted code."""
    if len(source_code.encode("utf-8")) > 200_000:
        raise ValueError("Scene DSL exceeds the 200000 byte limit")
    try:
        tree = ast.parse(source_code)
    except SyntaxError as exc:
        raise ValueError(f"Invalid Scene DSL syntax: {exc.msg} at line {exc.lineno}") from exc

    dsl_class: ast.ClassDef | None = None
    for statement in tree.body:
        if isinstance(statement, ast.ImportFrom):
            if statement.module != "shared.schemas.scene_dsl" or statement.level:
                raise ValueError("Only imports from shared.schemas.scene_dsl are allowed")
            imported = {alias.name for alias in statement.names}
            unknown = imported - set(_dsl_constructors())
            if unknown:
                raise ValueError(f"Unsupported Scene DSL imports: {sorted(unknown)}")
            continue
        if isinstance(statement, ast.ClassDef) and statement.name == "GeneratedSceneDSL":
            if dsl_class is not None:
                raise ValueError("Scene DSL must define GeneratedSceneDSL exactly once")
            dsl_class = statement
            continue
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
            if isinstance(statement.value.value, str):
                continue
        raise ValueError(f"Unsupported top-level Scene DSL statement: {type(statement).__name__}")

    if dsl_class is None:
        raise ValueError("Scene DSL must define class GeneratedSceneDSL")
    if dsl_class.bases or dsl_class.decorator_list or dsl_class.keywords:
        raise ValueError("GeneratedSceneDSL cannot use bases, decorators, or class keywords")

    dsl_data: dict[str, Any] = {
        "title": "Untitled Scene",
        "beats": [],
        "global_theme": None,
        "metadata": {},
        "version": "1.0",
    }
    for statement in dsl_class.body:
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
            if isinstance(statement.value.value, str):
                continue
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            raise ValueError("GeneratedSceneDSL may only contain simple field assignments")
        target = statement.targets[0]
        if not isinstance(target, ast.Name) or target.id not in _DSL_FIELDS:
            raise ValueError("GeneratedSceneDSL contains an unsupported field")
        dsl_data[target.id] = _evaluate_dsl_node(statement.value)

    return SceneDSL.model_validate(dsl_data)


def _validate_dsl_for_compilation(dsl: SceneDSL) -> None:
    catalog = build_primitives_catalog().primitives
    visual_types = {entry.name for entry in catalog if entry.module == "primitives.visual"}
    animation_types = {
        entry.name for entry in catalog if entry.module == "primitives.animation"
    } | {"wait"}
    for beat in dsl.beats:
        for element in beat.visual_elements:
            if element.type not in visual_types:
                raise ValueError(f"Unsupported visual primitive: {element.type}")
            invalid_params = [key for key in element.params if not _SAFE_PARAM_NAME.fullmatch(key)]
            if invalid_params:
                raise ValueError(f"Invalid visual parameter names: {invalid_params}")
        for animation in beat.animations:
            if animation.animation_type not in animation_types:
                raise ValueError(f"Unsupported animation primitive: {animation.animation_type}")
            invalid_params = [
                key for key in animation.params if not _SAFE_PARAM_NAME.fullmatch(key)
            ]
            if invalid_params:
                raise ValueError(f"Invalid animation parameter names: {invalid_params}")


def compile_dsl_to_manim(dsl: SceneDSL) -> str:
    """Deterministic compilation of SceneDSL Pydantic structure to standard Manim code."""
    _validate_dsl_for_compilation(dsl)
    lines = [
        "from __future__ import annotations",
        "from manim import *",
        "from primitives.visual import *",
        "from primitives.animation import *",
        "import numpy as np",
        "",
    ]

    # MovingCameraScene if any beat requests camera control
    has_camera = any(beat.camera is not None for beat in dsl.beats)
    base_class = "MovingCameraScene" if has_camera else "Scene"

    lines.append(f"class GeneratedScene({base_class}):")
    lines.append("    def construct(self):")
    lines.append("        self.elements = {}")

    # Injected beat durations (so that pipeline validation / rendering can use it)
    beat_durations = {beat.id: beat.duration_seconds for beat in dsl.beats}
    lines.append("        # BEAT_DURATIONS auto-injected by compiler")
    lines.append(f"        # BEAT_DURATIONS = {repr(beat_durations)}")
    lines.append("")

    for beat in dsl.beats:
        lines.append(f"        # === Beat: {beat.label!r} ({beat.id}) ===")
        if beat.narration:
            lines.append(f"        # Narration: {beat.narration!r}")

        # Camera settings
        if beat.camera:
            cam = beat.camera
            if cam.position:
                lines.append(f"        self.camera.frame.move_to(np.array({list(cam.position)}))")
            if cam.zoom is not None:
                lines.append(
                    f"        self.camera.frame.set_width(self.camera.frame.width / {cam.zoom})"
                )

        # Instantiate Visual Elements
        for elem in beat.visual_elements:
            args = []
            for k, v in elem.params.items():
                args.append(f"{k}={format_arg(v)}")
            arg_str = ", ".join(args)

            elem_key = repr(elem.id)
            lines.append(f"        self.elements[{elem_key}] = {elem.type}({arg_str})")

            # Apply Position
            if elem.position:
                pos = elem.position
                if pos.relative_to and pos.target_id:
                    dir_map = {
                        "left_of": "LEFT",
                        "right_of": "RIGHT",
                        "above": "UP",
                        "below": "DOWN",
                    }
                    direction = dir_map.get(pos.relative_to, "UP")
                    lines.append(
                        f"        self.elements[{elem_key}].next_to("
                        f"self.elements[{pos.target_id!r}], {direction}, buff={pos.buff})"
                    )
                else:
                    lines.append(
                        f"        self.elements[{elem_key}].move_to("
                        f"np.array([{pos.x}, {pos.y}, {pos.z}]))"
                    )

        # Compile Animations
        current_group: list[str] = []
        for anim in beat.animations:
            if anim.animation_type == "wait":
                if current_group:
                    lines.append(f"        self.play({', '.join(current_group)})")
                    current_group = []
                rt_str = f"run_time={anim.run_time}" if anim.run_time is not None else ""
                lines.append(f"        self.wait({rt_str})")
                continue

            if anim.animation_type in SCENE_PLAYING_ANIMATIONS:
                # Flush previous group
                if current_group:
                    lines.append(f"        self.play({', '.join(current_group)})")
                    current_group = []

                # Call directly
                args = ["self"]
                target_exprs = []
                for tid in anim.target_ids:
                    target_exprs.append(f"self.elements[{tid!r}]")

                if target_exprs:
                    if len(target_exprs) == 1:
                        args.append(target_exprs[0])
                    else:
                        args.append(f"VGroup({', '.join(target_exprs)})")

                for k, v in anim.params.items():
                    args.append(f"{k}={format_arg(v)}")

                if anim.run_time is not None:
                    if anim.animation_type == "focus_zoom":
                        args.append(f"duration={anim.run_time}")
                    else:
                        args.append(f"run_time={anim.run_time}")

                lines.append(f"        {anim.animation_type}({', '.join(args)})")
                continue

            # Standard animation returning Animation object
            for tid in anim.target_ids:
                args = [f"self.elements[{tid!r}]"]
                for k, v in anim.params.items():
                    args.append(f"{k}={format_arg(v)}")

                if anim.run_time is not None:
                    if anim.animation_type in (
                        "cinematic_fade_in",
                        "cinematic_fade_out",
                        "cinematic_entrance",
                    ):
                        args.append(f"duration={anim.run_time}")
                    else:
                        args.append(f"run_time={anim.run_time}")

                current_group.append(f"{anim.animation_type}({', '.join(args)})")

            if not anim.simultaneous:
                if current_group:
                    lines.append(f"        self.play({', '.join(current_group)})")
                    current_group = []

        # Flush group at end of beat
        if current_group:
            lines.append(f"        self.play({', '.join(current_group)})")

        # Handle Transition out
        if beat.transition_out:
            spec = beat.transition_out
            if spec.transition_type == "fade_out":
                tids = [elem.id for elem in beat.visual_elements]
                if tids:
                    fade_outs = ", ".join(f"FadeOut(self.elements[{tid!r}])" for tid in tids)
                    lines.append(f"        self.play({fade_outs}, run_time={spec.duration})")

        lines.append("")

    return "\n".join(lines)
