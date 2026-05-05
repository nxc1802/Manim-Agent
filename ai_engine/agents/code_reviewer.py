from __future__ import annotations

import json
import logging
from typing import Any

from shared.pipeline_log import pipeline_debug
from shared.schemas.review import ReviewResult

from ai_engine.llm_client import LLMClient
from ai_engine.prompts import PROMPT_VERSION_CODE_REVIEWER, load_prompt_text

logger = logging.getLogger(__name__)


async def run_code_reviewer(
    *,
    llm: LLMClient,
    model: str,
    temperature: float,
    max_tokens: int,
    manim_code: str,
    error_logs: str | None = None,
    use_primitives: bool = True,
    request_timeout_seconds: int | None = None,
) -> tuple[ReviewResult, str, dict[str, Any], str, str]:
    """
    Analyzes Manim code for logic errors, render failures, and security violations.
    Returns (ReviewResult, prompt_version, llm_metrics, system_prompt, user_prompt).
    """

    # 1. Load prompts
    system = load_prompt_text("code_reviewer_system.txt")

    user = (
        "You are an expert Manim developer and code auditor. "
        "Review the following Manim Python code for:\n"
        "1. Logic and Manim-specific correctness.\n"
        "2. Render issues and syntax errors.\n"
        "3. Security and Sandbox violations (e.g., forbidden imports like "
        "'os', 'subprocess', 'sys', or file system access).\n\n"
        "Analyze the code carefully. If the code failed to render, "
        "identify the root cause from the logs and suggest a fix. "
        "Return issues in the specified JSON format. If there's a render error, "
        "you MUST return at least one issue describing the error.\n\n"
        f"### 📝 MANIM_CODE\n```python\n{manim_code}\n```\n"
    )

    if error_logs:
        user += f"\n### ❌ RENDER_ERROR_LOGS\n```\n{error_logs}\n```\n"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    pipeline_debug(
        "ai_engine.code_reviewer",
        "llm_input",
        "Code Reviewer LLM Inputs",
        details={"model": model, "messages": messages},
    )

    # 2. Execute LLM call
    comp = await llm.acomplete_chat_ex(
        model=model,
        messages=messages,
        json_mode=True,
        temperature=temperature,
        max_tokens=max_tokens,
        request_timeout_seconds=request_timeout_seconds,
    )

    pipeline_debug(
        "ai_engine.code_reviewer",
        "llm_output",
        "Code Reviewer LLM Output",
        details={"raw_json": comp.text},
    )

    # 3. Parse result
    try:
        # LiteLLM might return markdown code blocks in some models even with json_mode=True
        clean_text = comp.text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:].strip()
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3].strip()

        data = json.loads(clean_text)
        result = ReviewResult.model_validate(data)
    except Exception as e:
        logger.error(f"Failed to parse Code Reviewer output: {e}. Raw: {comp.text}")
        # Return empty issues as fallback to avoid crashing the pipeline
        result = ReviewResult(issues=[])

    metrics = {
        "duration_ms": comp.usage.duration_ms,
        "prompt_tokens": comp.usage.prompt_tokens,
        "completion_tokens": comp.usage.completion_tokens,
    }

    return result, PROMPT_VERSION_CODE_REVIEWER, metrics, system, user
