from typing import Any

from primitives.registry import build_primitives_catalog
from shared.pipeline_log import pipeline_debug
from shared.schemas.planner_output import PlannerOutput

from ai_engine.llm_client import LLMClient
from ai_engine.prompts import PROMPT_VERSION_PLANNER, load_prompt_text


async def run_planner(
    *,
    llm: LLMClient,
    model: str,
    temperature: float,
    max_tokens: int,
    storyboard_text: str,
    use_primitives: bool = True,
    request_timeout_seconds: int | None = None,
) -> tuple[PlannerOutput, str, dict[str, Any], str, str]:
    """Return (parsed planner output, prompt_version, metrics, system_prompt, user_prompt)."""
    if use_primitives:
        catalog = build_primitives_catalog()
        catalog_json = catalog.model_dump_json(indent=2)
        system = load_prompt_text("planner_system.txt")
        system_with_catalog = f"{system}\n\nAVAILABLE PRIMITIVES CATALOG:\n{catalog_json}"
    else:
        system_with_catalog = load_prompt_text("planner_system_no_primitives.txt")

    pipeline_debug(
        "ai_engine.planner",
        "llm_input",
        "Planner LLM Inputs",
        details={"model": model, "system": system_with_catalog, "user": storyboard_text},
    )

    completion = await llm.acomplete_ex(
        model=model,
        system=system_with_catalog,
        user=storyboard_text,
        json_mode=True,
        temperature=temperature,
        max_tokens=max_tokens,
        request_timeout_seconds=request_timeout_seconds,
    )

    pipeline_debug(
        "ai_engine.planner",
        "llm_output",
        "Planner LLM Output",
        details={"raw_json": completion.text},
    )

    metrics = {
        "duration_ms": completion.usage.duration_ms,
        "prompt_tokens": completion.usage.prompt_tokens,
        "completion_tokens": completion.usage.completion_tokens,
    }

    from ai_engine.json_utils import parse_json_object

    data = parse_json_object(completion.text)

    # Fallback for local LLMs that might output "scenes" instead of "beats"
    if "beats" not in data and "scenes" in data:
        data["beats"] = data.pop("scenes")

    if "beats" in data and isinstance(data["beats"], list):
        for beat in data["beats"]:
            if "step_label" not in beat and "scene_title" in beat:
                beat["step_label"] = beat.pop("scene_title")
            if "step_label" not in beat and "title" in beat:
                beat["step_label"] = beat.pop("title")

    plan = PlannerOutput.model_validate(data)
    return plan, PROMPT_VERSION_PLANNER, metrics, system_with_catalog, storyboard_text
