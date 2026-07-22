from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from app.config import settings


@dataclass(frozen=True)
class AgentModel:
    model: str
    temperature: float
    max_tokens: int
    reasoning_effort: str


@dataclass(frozen=True)
class ModelTier:
    """One model tier in the review-loop escalation chain."""

    model: str
    max_attempts: int
    reasoning_effort: str = "none"


def _load_yaml() -> dict[str, Any]:
    return yaml.safe_load(settings.agent_models_path.read_text(encoding="utf-8")) or {}


def load_agent_model(kind: str) -> AgentModel:
    data = _load_yaml()
    defaults = data.get("defaults") if isinstance(data.get("defaults"), dict) else {}
    agents = data.get("agents") if isinstance(data.get("agents"), dict) else {}
    config = agents.get(kind) if isinstance(agents.get(kind), dict) else {}

    model = config.get("model")
    if not model:
        tiers = load_review_loop_tiers(kind)
        model = tiers[0].model if tiers else (defaults.get("model") or settings.default_chat_model)

    return AgentModel(
        model=str(model),
        temperature=float(config.get("temperature", defaults.get("temperature", 0.3))),
        max_tokens=int(config.get("max_tokens", defaults.get("max_tokens", 4096))),
        reasoning_effort=str(
            config.get("reasoning_effort", defaults.get("reasoning_effort", "high"))
        ),
    )


def load_review_loop_tiers(kind: str | None = None) -> list[ModelTier]:
    """Load model escalation tiers from ``agent_models.yaml``.

    Checks agent-specific ``review_tiers`` under ``agents.<kind>`` first,
    then falls back to top-level ``review_loop.tiers`` or defaults.
    """
    data = _load_yaml()
    raw_tiers = None
    agents = data.get("agents")
    if isinstance(agents, dict):
        target_kind = kind or "code_reviewer"
        agent_data = agents.get(target_kind)
        if isinstance(agent_data, dict):
            raw_tiers = agent_data.get("review_tiers") or agent_data.get("tiers")

    if not isinstance(raw_tiers, list) or not raw_tiers:
        review_loop = data.get("review_loop")
        if isinstance(review_loop, dict):
            raw_tiers = review_loop.get("tiers")

    if not isinstance(raw_tiers, list) or not raw_tiers:
        return _default_tiers()

    tiers: list[ModelTier] = []
    for idx, item in enumerate(raw_tiers):
        if not isinstance(item, dict):
            continue
        model = str(item.get("model") or settings.default_chat_model)
        is_last = idx == len(raw_tiers) - 1
        default_max = settings.review_loop_final_tier_max_attempts if is_last else 1
        max_attempts = int(item.get("max_attempts", default_max))
        tiers.append(
            ModelTier(
                model=model,
                max_attempts=max_attempts,
                reasoning_effort=str(item.get("reasoning_effort", "high")),
            )
        )
    return tiers or _default_tiers()


def _default_tiers() -> list[ModelTier]:
    return [
        ModelTier(model="gemma-4-31b-it", max_attempts=1, reasoning_effort="none"),
        ModelTier(model="gemini-3-flash-preview", max_attempts=1, reasoning_effort="low"),
        ModelTier(
            model="gemini-3.5-flash",
            max_attempts=settings.review_loop_final_tier_max_attempts,
            reasoning_effort="medium",
        ),
    ]
