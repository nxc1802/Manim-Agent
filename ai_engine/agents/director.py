from __future__ import annotations
from ai_engine.llm_client import LLMClient
from ai_engine.prompts import PROMPT_VERSION_DIRECTOR, load_prompt_text
from shared.pipeline_log import pipeline_debug

def run_director(
    *,
    llm: LLMClient,
    model: str,
    temperature: float,
    max_tokens: int,
    project_title: str,
    project_description: str | None,
    extra_brief: str | None,
) -> tuple[str, str]:
    """Return (storyboard_markdown, prompt_version)."""
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
    
    text = llm.complete(
        model=model,
        system=system,
        user=user,
        json_mode=False,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    
    pipeline_debug(
        "ai_engine.director",
        "llm_output",
        "Director LLM Output",
        details={"text": text}
    )
    
    return text.strip(), PROMPT_VERSION_DIRECTOR
