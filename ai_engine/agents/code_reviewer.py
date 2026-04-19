from __future__ import annotations

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
    request_timeout_seconds: int | None = None,
) -> tuple[ReviewResult, str, dict[str, int | None]]:
    system = load_prompt_text("code_reviewer_system.txt")
    user = f"```python\n{manim_code}\n```"
    comp = llm.complete_ex(
        model=model,
        system=system,
        user=user,
        json_mode=True,
        temperature=temperature,
        max_tokens=max_tokens,
        request_timeout_seconds=request_timeout_seconds,
    )
    data = parse_json_object(comp.text)
    metrics: dict[str, int | None] = {
        "duration_ms": comp.usage.duration_ms,
        "prompt_tokens": comp.usage.prompt_tokens,
        "completion_tokens": comp.usage.completion_tokens,
    }
    return ReviewResult.model_validate(data), PROMPT_VERSION_CODE_REVIEWER, metrics
