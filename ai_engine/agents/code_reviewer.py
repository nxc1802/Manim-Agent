from __future__ import annotations

from shared.pipeline_log import pipeline_debug
from shared.schemas.review import ReviewResult

from ai_engine.json_utils import parse_json_object
from ai_engine.llm_client import LLMClient
from ai_engine.prompts import PROMPT_VERSION_CODE_REVIEWER, load_prompt_text


def run_code_reviewer(
    *,
    llm: LLMClient,
    model: str,
    temperature: float,
    max_tokens: int,
    manim_code: str,
    error_logs: str | None = None,
    request_timeout_seconds: int | None = None,
) -> tuple[ReviewResult, str, dict[str, int | None]]:
    system = load_prompt_text("code_reviewer_system.txt")
    user_parts = [f"```python\n{manim_code}\n```"]
    if error_logs:
        user_parts.append(f"\nRENDER ERROR LOGS:\n```\n{error_logs}\n```")
    user = "\n".join(user_parts)
    
    pipeline_debug(
        "ai_engine.code_reviewer",
        "llm_input",
        "Code Reviewer LLM Inputs",
        details={"model": model, "system": system, "user": user}
    )
    
    comp = llm.complete_ex(
        model=model,
        system=system,
        user=user,
        json_mode=True,
        temperature=temperature,
        max_tokens=max_tokens,
        request_timeout_seconds=request_timeout_seconds,
    )
    
    pipeline_debug(
        "ai_engine.code_reviewer",
        "llm_output",
        "Code Reviewer LLM Output",
        details={"raw_json": comp.text}
    )
    
    data = parse_json_object(comp.text)
    metrics: dict[str, int | None] = {
        "duration_ms": comp.usage.duration_ms,
        "prompt_tokens": comp.usage.prompt_tokens,
        "completion_tokens": comp.usage.completion_tokens,
    }
    try:
        res = ReviewResult.model_validate(data)
    except Exception:
        pipeline_debug("ai_engine.code_reviewer", "validation_failed", "Pydantic validation failed for Code Reviewer output")
        # Fallback to empty issues to allow the loop to continue or fail gracefully
        res = ReviewResult(issues=[])
    
    return res, PROMPT_VERSION_CODE_REVIEWER, metrics
