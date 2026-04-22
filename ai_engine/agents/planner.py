from __future__ import annotations
from shared.schemas.planner_output import PlannerOutput
from ai_engine.llm_client import LLMClient
from ai_engine.prompts import PROMPT_VERSION_PLANNER, load_prompt_text
from shared.pipeline_log import pipeline_debug

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
    
    pipeline_debug(
        "ai_engine.planner",
        "llm_input",
        "Planner LLM Inputs",
        details={"model": model, "system": system, "user": storyboard_text}
    )
    
    raw = llm.complete(
        model=model,
        system=system,
        user=storyboard_text,
        json_mode=True,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    
    pipeline_debug(
        "ai_engine.planner",
        "llm_output",
        "Planner LLM Output",
        details={"raw_json": raw}
    )
    
    from ai_engine.json_utils import parse_json_object
    data = parse_json_object(raw)
    plan = PlannerOutput.model_validate(data)
    return plan, PROMPT_VERSION_PLANNER
