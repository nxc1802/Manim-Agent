from typing import Any

from shared.pipeline_log import pipeline_debug

from ai_engine.llm_client import LLMClient
from ai_engine.prompts import PROMPT_VERSION_DIRECTOR, load_prompt_text


async def run_director(
    *,
    llm: LLMClient,
    model: str,
    temperature: float,
    max_tokens: int,
    project_title: str,
    project_description: str | None,
    target_scenes: int | None = None,
    extra_brief: str | None = None,
    request_timeout_seconds: int | None = None,
) -> tuple[str, str, dict[str, Any], str, str]:
    """Return (storyboard_markdown, prompt_version, metrics, system_prompt, user_prompt)."""
    system = load_prompt_text("director_system.txt")
    if target_scenes:
        system = system.replace("{{target_scenes}}", str(target_scenes))
    else:
        system = system.replace("{{target_scenes}}", "4") # Default fallback

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
    
    completion = await llm.acomplete_ex(
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
    
    return completion.text.strip(), PROMPT_VERSION_DIRECTOR, metrics, system, user
