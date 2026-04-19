from __future__ import annotations

from shared.schemas.planner_output import PlannerOutput

from ai_engine.llm_client import LLMClient
from ai_engine.prompts import PROMPT_VERSION_PLANNER, load_prompt_text


def run_planner(
    *,
    llm: LLMClient,
    model: str,
    temperature: float,
    max_tokens: int,
    storyboard_text: str,
) -> tuple[PlannerOutput, str]:
    """Return (parsed planner output, prompt_version)."""
    system = load_prompt_text("planner_system.txt")
    raw = llm.complete(
        model=model,
        system=system,
        user=storyboard_text,
        json_mode=True,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    plan = PlannerOutput.model_validate_json(raw)
    return plan, PROMPT_VERSION_PLANNER
