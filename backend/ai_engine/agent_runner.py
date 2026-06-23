from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from pydantic import BaseModel
from shared.pipeline_log import pipeline_event

from ai_engine.json_utils import parse_json_object

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


async def _run_agent_with_self_correction(
    agent_name: str,
    call_fn: Callable[..., Awaitable[tuple[Any, str, dict[str, Any], str, str]]],
    schema: type[T] | None,
    **kwargs: Any,
) -> tuple[T | Any, str, dict[str, Any], str, str]:
    """Helper to call agent and validate schema, with structured logging."""
    start_time = time.monotonic()
    logger.info(
        f"Invoking agent {agent_name}",
        extra={
            "agent_name": agent_name,
            "inputs": {
                k: str(v)[:200]
                for k, v in kwargs.items()
                if k not in ("llm", "code_llm", "visual_llm")
            },
        },
    )
    try:
        result, version, metrics, system, user = await call_fn(**kwargs)
        elapsed = time.monotonic() - start_time

        if schema is None:
            logger.info(
                f"Agent {agent_name} invocation succeeded (no schema validation)",
                extra={
                    "agent_name": agent_name,
                    "duration_seconds": elapsed,
                    "metrics": metrics,
                },
            )
            return result, version, metrics, system, user

        validated: T
        if isinstance(result, str):
            data = parse_json_object(result)
            validated = schema.model_validate(data)
        else:
            if isinstance(result, schema):
                validated = result
            else:
                validated = schema.model_validate(result)

        logger.info(
            f"Agent {agent_name} invocation succeeded with validation",
            extra={
                "agent_name": agent_name,
                "duration_seconds": elapsed,
                "metrics": metrics,
                "schema": schema.__name__,
            },
        )
        return validated, version, metrics, system, user

    except Exception as e:
        elapsed = time.monotonic() - start_time
        logger.error(
            f"Agent {agent_name} failed: {str(e)}",
            extra={"agent_name": agent_name, "duration_seconds": elapsed, "error": str(e)},
        )
        pipeline_event(
            f"ai_engine.{agent_name}",
            "agent_failed",
            "Agent call or validation failed",
            details={"error": str(e)},
        )
        raise
