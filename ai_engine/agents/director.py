from __future__ import annotations

from shared.pipeline_log import pipeline_debug

from ai_engine.llm_client import LLMClient
from ai_engine.prompts import PROMPT_VERSION_DIRECTOR, load_prompt_text


def run_director(
    *,
    llm: LLMClient,
    model: str,
    temperature: float,
    max_tokens: int,
    project_title: str,
    project_description: str | None,
    extra_brief: str | None,
    request_timeout_seconds: int | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """Return (storyboard_markdown, prompt_version, metrics)."""
    system = load_prompt_text("director_system.txt")
    user_parts = [
        f"Project title: {project_title}",
        f"Project description: {project_description or ''}",
    ]
    if extra_brief:
        user_parts.append(f"Additional brief:\n{extra_brief}")
    user = "\n".join(user_parts)
    
    pipeline_debug(
        "ai_engine.director",
        "llm_input",
        "Director LLM Inputs",
        details={"model": model, "system": system, "user": user}
    )
    
    completion = llm.complete_ex(
        model=model,
        system=system,
        user=user,
        json_mode=False,
        temperature=temperature,
        max_tokens=max_tokens,
        request_timeout_seconds=request_timeout_seconds,
    )
    
    pipeline_debug(
        "ai_engine.director",
        "llm_output",
        "Director LLM Output",
        details={"text": completion.text}
    )
    
    metrics = {
        "duration_ms": completion.usage.duration_ms,
        "prompt_tokens": completion.usage.prompt_tokens,
        "completion_tokens": completion.usage.completion_tokens,
    }
    
    return completion.text.strip(), PROMPT_VERSION_DIRECTOR, metrics
