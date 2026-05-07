from __future__ import annotations

from typing import Any

from shared.pipeline_log import pipeline_debug
from shared.schemas.review import ReviewResult

from ai_engine.json_utils import parse_json_object
from ai_engine.llm_client import LLMClient
from ai_engine.prompts import PROMPT_VERSION_VISUAL_REVIEWER, load_prompt_text


async def run_visual_reviewer(
    *,
    llm: LLMClient,
    model: str,
    temperature: float,
    max_tokens: int,
    frame_jpeg: bytes,
    context: str | None = None,
    request_timeout_seconds: int | None = None,
) -> tuple[ReviewResult, str, dict[str, Any], str, str]:
    """Vision review on JPEG frame (default: last frame of preview ≈ end of Scene.play())."""
    system = load_prompt_text("visual_reviewer_system.txt")
    user_instruction = (
        "You are an expert Manim developer. "
        "Review the following preview frame from an educational scene. "
        "Analyze the visuals for correctness, clarity, and alignment with the intended message. "
        "Return issues in the specified JSON format."
    )
    user = f"{user_instruction}\n\nContext: {context}" if context else user_instruction

    pipeline_debug(
        "ai_engine.visual_reviewer",
        "llm_input",
        "Visual Reviewer LLM Inputs",
        details={"model": model, "system": system, "user": user, "image_size": len(frame_jpeg)},
    )

    comp = await llm.acomplete_with_images_ex(
        model=model,
        system=system,
        user=user,
        image_jpeg=frame_jpeg,
        json_mode=True,
        temperature=temperature,
        max_tokens=max_tokens,
        request_timeout_seconds=request_timeout_seconds,
    )

    pipeline_debug(
        "ai_engine.visual_reviewer",
        "llm_output",
        "Visual Reviewer LLM Output",
        details={"raw_json": comp.text},
    )

    data = parse_json_object(comp.text, list_key="issues")
    metrics: dict[str, int | None] = {
        "duration_ms": comp.usage.duration_ms,
        "prompt_tokens": comp.usage.prompt_tokens,
        "completion_tokens": comp.usage.completion_tokens,
    }
    try:
        res = ReviewResult.model_validate(data)
    except Exception as e:
        pipeline_debug(
            "ai_engine.visual_reviewer",
            "validation_failed",
            f"Pydantic validation failed for Visual Reviewer output: {e}",
            details={"data": data},
        )
        # Fallback to empty issues to allow the loop to continue or fail gracefully
        res = ReviewResult(issues=[])

    return res, PROMPT_VERSION_VISUAL_REVIEWER, metrics, system, user
