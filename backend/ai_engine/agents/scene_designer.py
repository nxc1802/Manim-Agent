from __future__ import annotations

import json
from typing import Any, cast

from primitives.registry import build_primitives_catalog
from shared.pipeline_log import pipeline_debug
from shared.schemas.planner_output import PlannerOutput

from ai_engine.llm_client import LLMClient
from ai_engine.prompts import PROMPT_VERSION_SCENE_DESIGNER, load_prompt_text


async def run_scene_designer(
    *,
    llm: LLMClient,
    model: str,
    temperature: float,
    max_tokens: int,
    planner: PlannerOutput,
    sync_segments: dict[str, Any] | list[Any] | None,
    storyboard_excerpt: str | None,
    request_timeout_seconds: int | None = None,
) -> tuple[str, str, dict[str, Any], str, str]:
    """Return (dsl_python_source, prompt_version, llm_metrics, system_prompt, user_prompt)."""
    system_base = load_prompt_text("scene_designer_system.txt")

    catalog = build_primitives_catalog().model_dump(mode="json")
    catalog_str = f"### 📦 PRIMITIVES_CATALOG\n{json.dumps(catalog, indent=2)}\n\n"

    goal = {
        "planner_output": planner.model_dump(mode="json"),
        "sync_segments": sync_segments,
        "storyboard_excerpt": storyboard_excerpt,
    }

    system = f"{system_base}\n\n{catalog_str}### 🎯 ORIGINAL_GOAL\n{json.dumps(goal, indent=2)}"
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": "Design the scene and generate the GeneratedSceneDSL Python class.",
        },
    ]

    pipeline_debug(
        "ai_engine.scene_designer",
        "llm_input",
        "Scene Designer LLM Input",
        details={"model": model, "messages": messages},
    )

    comp = await cast(Any, llm).acomplete_chat_ex(
        model=model,
        messages=messages,
        json_mode=False,
        temperature=temperature,
        max_tokens=max_tokens,
        request_timeout_seconds=request_timeout_seconds,
        agent_name="scene_designer",
    )

    pipeline_debug(
        "ai_engine.scene_designer",
        "llm_output",
        "Scene Designer LLM Output",
        details={"text": comp.text},
    )

    metrics: dict[str, int | None] = {
        "duration_ms": comp.usage.duration_ms,
        "prompt_tokens": comp.usage.prompt_tokens,
        "completion_tokens": comp.usage.completion_tokens,
    }

    user_prompt = messages[-1]["content"] if messages else ""
    return comp.text.strip(), PROMPT_VERSION_SCENE_DESIGNER, metrics, system, user_prompt
