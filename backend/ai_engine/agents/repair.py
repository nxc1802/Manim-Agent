from __future__ import annotations

from typing import Any, cast

from shared.code_utils import extract_python_code
from shared.pipeline_log import pipeline_debug
from shared.schemas.validation import ValidationIssue

from ai_engine.llm_client import LLMClient
from ai_engine.prompts import PROMPT_VERSION_REPAIR, load_prompt_text


async def run_repair(
    *,
    llm: LLMClient,
    model: str,
    temperature: float,
    max_tokens: int,
    original_code: str,
    validation_errors: list[ValidationIssue],
    error_logs: str | None = None,
    request_timeout_seconds: int | None = None,
) -> tuple[str, str, dict[str, Any], str, str]:
    """Attempt to fix validation errors without a full rebuild of the scene."""
    system = load_prompt_text("repair_system.txt")

    # Format errors for user prompt
    errors_str = ""
    for idx, err in enumerate(validation_errors, 1):
        line_info = f" (line {err.line})" if err.line is not None else ""
        errors_str += f"{idx}. [{err.code}] {err.message}{line_info}\n"

    user_parts = [
        "--- ORIGINAL CODE ---",
        original_code,
        "",
        "--- VALIDATION ERRORS ---",
        errors_str,
    ]
    if error_logs:
        user_parts.append(f"\n--- ERROR LOGS ---\n{error_logs}")

    user = "\n".join(user_parts)

    pipeline_debug(
        "ai_engine.repair",
        "llm_input",
        "Repair LLM Inputs",
        details={"model": model, "system": system, "user": user},
    )

    completion = await cast(Any, llm).acomplete_ex(
        model=model,
        system=system,
        user=user,
        json_mode=False,
        temperature=temperature,
        max_tokens=max_tokens,
        request_timeout_seconds=request_timeout_seconds,
        agent_name="repair",
    )

    pipeline_debug(
        "ai_engine.repair",
        "llm_output",
        "Repair LLM Output",
        details={"text": completion.text},
    )

    metrics = {
        "duration_ms": completion.usage.duration_ms,
        "prompt_tokens": completion.usage.prompt_tokens,
        "completion_tokens": completion.usage.completion_tokens,
    }

    # Extract python code block
    repaired_code = extract_python_code(completion.text)
    if not repaired_code.strip():
        repaired_code = completion.text

    return repaired_code.strip(), PROMPT_VERSION_REPAIR, metrics, system, user
