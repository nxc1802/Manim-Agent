from __future__ import annotations

from shared.schemas.review import ReviewResult

from ai_engine.json_utils import parse_json_object
from ai_engine.llm_client import LLMClient
from ai_engine.prompts import PROMPT_VERSION_VISUAL_REVIEWER, load_prompt_text


def run_visual_reviewer(
    *,
    llm: LLMClient,
    model: str,
    temperature: float,
    max_tokens: int,
    frame_jpeg: bytes,
    context: str | None = None,
    request_timeout_seconds: int | None = None,
) -> tuple[ReviewResult, str, dict[str, int | None]]:
    """Vision review on JPEG frame (default: last frame of preview ≈ end of Scene.play())."""
    system = load_prompt_text("visual_reviewer_system.txt")
    user = context or "Review this preview frame from a Manim educational scene."
    comp = llm.complete_with_images_ex(
        model=model,
        system=system,
        user=user,
        image_jpeg=frame_jpeg,
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
    return ReviewResult.model_validate(data), PROMPT_VERSION_VISUAL_REVIEWER, metrics
