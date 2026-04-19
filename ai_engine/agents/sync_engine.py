from __future__ import annotations

import json
from typing import Any

from ai_engine.json_utils import parse_json_object
from ai_engine.llm_client import LLMClient
from ai_engine.prompts import PROMPT_VERSION_SYNC_ENGINE, load_prompt_text


def run_sync_engine(
    *,
    llm: LLMClient,
    model: str,
    temperature: float,
    max_tokens: int,
    planner_output: dict[str, Any] | list[Any],
    voice_timestamps: dict[str, Any] | list[Any] | None,
    voice_script: str | None,
    request_timeout_seconds: int | None = None,
) -> tuple[dict[str, Any], str, dict[str, int | None]]:
    """LLM merges planner + voice timing into `sync_segments` JSON (API process only)."""
    system = load_prompt_text("sync_engine_system.txt")
    user_obj: dict[str, Any] = {
        "planner_output": planner_output,
        "voice_timestamps": voice_timestamps,
        "voice_script": voice_script,
    }
    user = json.dumps(user_obj, ensure_ascii=False, indent=2)
    comp = llm.complete_ex(
        model=model,
        system=system,
        user=user,
        json_mode=True,
        temperature=temperature,
        max_tokens=max_tokens,
        request_timeout_seconds=request_timeout_seconds,
    )
    segments = parse_json_object(comp.text)
    metrics: dict[str, int | None] = {
        "duration_ms": comp.usage.duration_ms,
        "prompt_tokens": comp.usage.prompt_tokens,
        "completion_tokens": comp.usage.completion_tokens,
    }
    return segments, PROMPT_VERSION_SYNC_ENGINE, metrics
