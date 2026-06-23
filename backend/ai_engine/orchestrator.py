from __future__ import annotations

from typing import Any

from shared.schemas.planner_output import PlannerOutput

from ai_engine.agent_runner import _run_agent_with_self_correction
from ai_engine.agents.director import run_director
from ai_engine.agents.planner import run_planner
from ai_engine.builder_loop import (
    run_builder_loop_phase as run_builder_loop_phase,
)
from ai_engine.builder_loop import (
    run_single_review_round as run_single_review_round,
)
from ai_engine.builder_loop import (
    run_single_review_round_ex as run_single_review_round_ex,
)
from ai_engine.builder_loop import (
    truncate_error_logs as truncate_error_logs,
)
from ai_engine.llm_client import LLMClient


async def run_storyboard_phase(
    *,
    llm: LLMClient,
    model: str,
    temperature: float,
    max_tokens: int,
    project_title: str,
    project_description: str | None,
    target_scenes: int | None = None,
    extra_brief: str | None = None,
) -> tuple[str, str, dict[str, Any], str, str]:
    """Phase 1: Storyboard generation via Director Agent."""
    return await _run_agent_with_self_correction(
        "director",
        run_director,
        schema=None,
        llm=llm,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        project_title=project_title,
        project_description=project_description,
        target_scenes=target_scenes,
        extra_brief=extra_brief,
    )


async def run_planning_phase(
    *,
    llm: LLMClient,
    model: str,
    temperature: float,
    max_tokens: int,
    storyboard_text: str,
    use_primitives: bool = True,
    request_timeout_seconds: int | None = None,
) -> tuple[PlannerOutput, str, dict[str, Any], str, str]:
    """Phase 2: Execution plan generation via Planner Agent."""
    return await _run_agent_with_self_correction(
        "planner",
        run_planner,
        schema=PlannerOutput,
        llm=llm,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        storyboard_text=storyboard_text,
        use_primitives=use_primitives,
        request_timeout_seconds=request_timeout_seconds,
    )
