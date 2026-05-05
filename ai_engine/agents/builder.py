from __future__ import annotations

import json
from typing import Any

from primitives.registry import build_primitives_catalog
from shared.pipeline_log import pipeline_debug
from shared.schemas.planner_output import PlannerOutput

from ai_engine.llm_client import LLMClient
from ai_engine.prompts import PROMPT_VERSION_BUILDER, load_prompt_text


async def run_builder(
    *,
    llm: LLMClient,
    model: str,
    temperature: float,
    max_tokens: int,
    planner: PlannerOutput,
    sync_segments: dict[str, Any] | list[Any] | None,
    storyboard_excerpt: str | None,
    use_primitives: bool = True,
    review_feedback: str | None = None,
    chat_history: list[dict[str, str]] | None = None,
    request_timeout_seconds: int | None = None,
    is_fix_mode: bool = False,
) -> tuple[str, str, dict[str, Any], str, str]:
    """Return (python_source, prompt_version, llm_metrics, system_prompt, user_prompt)."""
    
    # 1. Select Base System Prompt
    if is_fix_mode:
        system_base = load_prompt_text("builder_system_fix.txt")
    else:
        if use_primitives:
            system_base = load_prompt_text("builder_system.txt")
        else:
            system_base = load_prompt_text("builder_system_no_primitives.txt")
    
    # 2. Append Catalog (only if primitives are enabled AND it's NOT fix mode, or as per requirement)
    # Actually, in fix mode, it's better to keep catalog if using primitives to know what's available.
    catalog_str = ""
    if use_primitives:
        catalog = build_primitives_catalog().model_dump(mode="json")
        catalog_str = f"### 📦 PRIMITIVES_CATALOG\n{json.dumps(catalog, indent=2)}\n\n"
    
    # 3. Contextual Data
    goal = {
        "planner_output": planner.model_dump(mode="json"),
        "sync_segments": sync_segments,
        "storyboard_excerpt": storyboard_excerpt,
    }
    
    if is_fix_mode:
        # In Fix Mode, we emphasize the current state and feedback
        system = (
            f"{system_base}\n\n"
            f"{catalog_str}"
            f"### 🎯 ORIGINAL_GOAL_SUMMARY\n{planner.model_dump_json()[:1000]}..." # Compressed goal for fix mode
        )
        # We assume chat_history contains the [Assistant(code), User(feedback)]
        messages = [{"role": "system", "content": system}] + (chat_history or [])
    else:
        # Init Mode
        system = (
            f"{system_base}\n\n"
            f"{catalog_str}"
            f"### 🎯 ORIGINAL_GOAL\n{json.dumps(goal, indent=2)}"
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "Generate the first version of the Manim code based on the ORIGINAL_GOAL."},
        ]
    
    pipeline_debug(
        "ai_engine.builder",
        "llm_input",
        f"Builder LLM Input (Mode={'Fix' if is_fix_mode else 'Init'})",
        details={"model": model, "messages": messages}
    )
    
    comp = await llm.acomplete_chat_ex(
        model=model,
        messages=messages,
        json_mode=False,
        temperature=temperature,
        max_tokens=max_tokens,
        request_timeout_seconds=request_timeout_seconds,
    )
    
    pipeline_debug(
        "ai_engine.builder",
        "llm_output",
        "Builder LLM Output",
        details={"text": comp.text}
    )
    
    metrics: dict[str, int | None] = {
        "duration_ms": comp.usage.duration_ms,
        "prompt_tokens": comp.usage.prompt_tokens,
        "completion_tokens": comp.usage.completion_tokens,
    }
    user_prompt = messages[-1]["content"] if messages else ""
    return comp.text.strip(), PROMPT_VERSION_BUILDER, metrics, system, user_prompt
