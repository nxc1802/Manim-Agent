from __future__ import annotations

import logging
from typing import Any

from shared.schemas.scene_dsl import AnimationStep, Position, SceneDSL, SceneDSLBeat, VisualElement

logger = logging.getLogger(__name__)

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

        if hasattr(manim, val):
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


def parse_python_class_dsl(source_code: str) -> SceneDSL:
    """Execute Python class DSL code and parse it into a SceneDSL Pydantic model."""
    from shared.schemas.scene_dsl import (
        CameraState,
        ThemeConfig,
        TransitionSpec,
    )

    local_scope = {
        "SceneDSL": SceneDSL,
        "SceneDSLBeat": SceneDSLBeat,
        "VisualElement": VisualElement,
        "AnimationStep": AnimationStep,
        "Position": Position,
        "ThemeConfig": ThemeConfig,
        "CameraState": CameraState,
        "TransitionSpec": TransitionSpec,
    }

    # Execute the code safely using local_scope as both globals and locals
    exec(source_code, local_scope)

    # Find the class that represents the DSL (typically GeneratedSceneDSL, or any class with beats attribute)
    dsl_class = None
    for _name, obj in local_scope.items():
        if isinstance(obj, type) and hasattr(obj, "beats"):
            dsl_class = obj
            break

    if not dsl_class:
        raise ValueError("No class with 'beats' attribute found in the DSL code.")

    dsl_data = {
        "title": getattr(dsl_class, "title", "Untitled Scene"),
        "beats": getattr(dsl_class, "beats", []),
        "global_theme": getattr(dsl_class, "global_theme", None),
        "metadata": getattr(dsl_class, "metadata", {}),
        "version": getattr(dsl_class, "version", "1.0"),
    }

    return SceneDSL.model_validate(dsl_data)


def compile_dsl_to_manim(dsl: SceneDSL) -> str:
    """Deterministic compilation of SceneDSL Pydantic structure to standard Manim code."""
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
        lines.append(f"        # === Beat: {beat.label} ({beat.id}) ===")
        if beat.narration:
            lines.append(f"        # Narration: {beat.narration}")

        # Camera settings
        if beat.camera:
            cam = beat.camera
            if cam.position:
                lines.append(f"        self.camera.frame.move_to(np.array({list(cam.position)}))")
            if cam.zoom is not None:
                lines.append(f"        self.camera.frame.set_width(self.camera.frame.width / {cam.zoom})")

        # Instantiate Visual Elements
        for elem in beat.visual_elements:
            args = []
            for k, v in elem.params.items():
                args.append(f"{k}={format_arg(v)}")
            arg_str = ", ".join(args)

            lines.append(f"        self.elements[\"{elem.id}\"] = {elem.type}({arg_str})")

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
                        f"        self.elements[\"{elem.id}\"].next_to(self.elements[\"{pos.target_id}\"], {direction}, buff={pos.buff})"
                    )
                else:
                    lines.append(
                        f"        self.elements[\"{elem.id}\"].move_to(np.array([{pos.x}, {pos.y}, {pos.z}]))"
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
                    target_exprs.append(f"self.elements[\"{tid}\"]")

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
                args = [f"self.elements[\"{tid}\"]"]
                for k, v in anim.params.items():
                    args.append(f"{k}={format_arg(v)}")

                if anim.run_time is not None:
                    if anim.animation_type in ("cinematic_fade_in", "cinematic_fade_out", "cinematic_entrance"):
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
                    fade_outs = ", ".join(f"FadeOut(self.elements[\"{tid}\"])" for tid in tids)
                    lines.append(f"        self.play({fade_outs}, run_time={spec.duration})")

        lines.append("")

    return "\n".join(lines)
