from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from ai_engine.agents.director import run_director
from ai_engine.agents.planner import run_planner
from ai_engine.llm_client import LLMClient
from ai_engine.utils.storage_helper import save_agent_interaction
from shared.schemas.planner_output import PlannerOutput

logger = logging.getLogger(__name__)

async def _run_agent_with_self_correction(
    agent_name: str,
    call_fn: Any,
    schema: Any,
    **kwargs: Any
) -> tuple[Any, str, dict[str, Any], str, str]:
    """Helper to call agent and validate schema."""
    try:
        result, version, metrics, system, user = await call_fn(**kwargs)
        if schema is None:
            return result, version, metrics, system, user
        
        from ai_engine.json_utils import parse_json_object
        if isinstance(result, str):
            data = parse_json_object(result)
            validated = schema.model_validate(data)
            return validated, version, metrics, system, user
        else:
            if isinstance(result, schema):
                return result, version, metrics, system, user
            validated = schema.model_validate(result)
            return validated, version, metrics, system, user
    except Exception as e:
        logger.error(f"Agent {agent_name} failed: {str(e)}")
        raise

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

# Compatibility imports or re-exports
from ai_engine.builder_loop import (
    run_builder_loop_phase,
    run_single_review_round,
    run_single_review_round_ex,
)
