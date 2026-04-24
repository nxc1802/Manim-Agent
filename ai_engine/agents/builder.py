from __future__ import annotations

import json
from typing import Any

from primitives.registry import build_primitives_catalog
from shared.pipeline_log import pipeline_debug
from shared.schemas.planner_output import PlannerOutput

from ai_engine.llm_client import LLMClient
from ai_engine.prompts import PROMPT_VERSION_BUILDER, load_prompt_text


def run_builder(
    *,
    llm: LLMClient,
    model: str,
    temperature: float,
    max_tokens: int,
    planner: PlannerOutput,
    sync_segments: dict[str, Any] | list[Any] | None,
    storyboard_excerpt: str | None,
    review_feedback: str | None = None,
    chat_history: list[dict[str, str]] | None = None,
    request_timeout_seconds: int | None = None,
) -> tuple[str, str, dict[str, int | None]]:
    """Return (python_source, prompt_version, llm_metrics)."""
    system_base = load_prompt_text("builder_system.txt")
    catalog = build_primitives_catalog().model_dump(mode="json")
    
    # Original Goal: Fixed context for all rounds
    goal = {
        "planner_output": planner.model_dump(mode="json"),
        "sync_segments": sync_segments,
        "storyboard_excerpt": storyboard_excerpt,
    }
    
    system = (
        f"{system_base}\n\n"
        f"### 📦 PRIMITIVES_CATALOG\n{json.dumps(catalog, indent=2)}\n\n"
        f"### 🎯 ORIGINAL_GOAL\n{json.dumps(goal, indent=2)}"
    )

    if chat_history:
        # chat_history already contains [Assistant(vN-1), User(feedback_vN-1)]
        messages = [{"role": "system", "content": system}] + chat_history
    else:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "Generate the first version of the Manim code based on the ORIGINAL_GOAL."},
        ]
    
    pipeline_debug(
        "ai_engine.builder",
        "llm_input",
        "Builder LLM Chat Input (Conversational)",
        details={"model": model, "messages": messages}
    )
    
    comp = llm.complete_chat_ex(
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
    return comp.text.strip(), PROMPT_VERSION_BUILDER, metrics
