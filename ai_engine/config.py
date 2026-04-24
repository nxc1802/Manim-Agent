from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import yaml  # type: ignore[import-untyped]

AgentName = Literal[
    "director",
    "planner",
    "builder",
    "code_reviewer",
    "visual_reviewer",
    "voice",
]


@dataclass(frozen=True)
class AgentLLMParams:
    model: str
    temperature: float
    max_tokens: int


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_agent_models_path() -> Path:
    """Bundled example YAML; copy to `agent_models.yaml` and set AGENT_MODELS_YAML to override."""
    return Path(__file__).resolve().parent / "config" / "agent_models.example.yaml"


def load_agent_models_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = f"Invalid agent models YAML (expected mapping): {path}"
        raise ValueError(msg)
    return cast(dict[str, Any], data)


def resolve_agent_params(data: dict[str, Any], agent: AgentName) -> AgentLLMParams:
    defaults = cast(dict[str, Any], data.get("defaults") or {})
    agents = cast(dict[str, Any], data.get("agents") or {})
    agent_cfg = cast(dict[str, Any], agents.get(agent) or {})
    model = str(agent_cfg.get("model") or "openrouter/google/gemma-4-31b-it:free")
    temperature = float(
        agent_cfg.get("temperature", defaults.get("temperature", 0.4)),
    )
    max_tokens = int(agent_cfg.get("max_tokens", defaults.get("max_tokens", 4096)))
    return AgentLLMParams(model=model, temperature=temperature, max_tokens=max_tokens)




@dataclass(frozen=True)
class BuilderReviewLoopConfig:
    """Subset of ``builder_review_loop`` from agent_models YAML (Phase 8)."""

    max_rounds: int
    early_stop_require_all: tuple[str, ...]
    code_agent_blocking_issues_empty: bool
    code_static_ast_parse_ok: bool
    code_static_forbidden_imports_ok: bool
    visual_agent_blocking_issues_empty: bool
    blocking_severity_min: str
    stop_when_only_info_severity: bool
    on_max_rounds_exceeded: str


def load_builder_review_loop(data: dict[str, Any]) -> BuilderReviewLoopConfig:
    raw = cast(dict[str, Any], data.get("builder_review_loop") or {})
    max_rounds = int(raw.get("max_rounds") or 3)
    early = cast(dict[str, Any], raw.get("early_stop") or {})
    req = early.get("require_all") or ["code_review_passed", "visual_review_passed"]
    if not isinstance(req, list):
        req = ["code_review_passed", "visual_review_passed"]
    pass_c = cast(dict[str, Any], raw.get("pass_criteria") or {})
    code_p = cast(dict[str, Any], pass_c.get("code_review_passed") or {})
    vis_p = cast(dict[str, Any], pass_c.get("visual_review_passed") or {})
    return BuilderReviewLoopConfig(
        max_rounds=max_rounds,
        early_stop_require_all=tuple(str(x) for x in req),
        code_agent_blocking_issues_empty=bool(code_p.get("agent_blocking_issues_empty", True)),
        code_static_ast_parse_ok=bool(code_p.get("static_ast_parse_ok", True)),
        code_static_forbidden_imports_ok=bool(code_p.get("static_forbidden_imports_ok", True)),
        visual_agent_blocking_issues_empty=bool(vis_p.get("agent_blocking_issues_empty", True)),
        blocking_severity_min=str(raw.get("blocking_severity_min") or "warning"),
        stop_when_only_info_severity=bool(raw.get("stop_when_only_info_severity", False)),
        on_max_rounds_exceeded=str(raw.get("on_max_rounds_exceeded") or "hitl_or_fail"),
    )


@dataclass(frozen=True)
class RuntimeLimitsConfig:
    """Single source for worker subprocess, poll, and per-agent LLM HTTP timeouts (seconds)."""

    worker_man_render_timeout_seconds: int
    worker_tts_subprocess_timeout_seconds: int
    preview_poll_timeout_seconds: float
    preview_poll_interval_seconds: float
    llm_timeout_default_seconds: int
    llm_timeouts: dict[str, int]

    def llm_timeout_seconds(self, agent: str) -> int:
        return int(self.llm_timeouts.get(agent, self.llm_timeout_default_seconds))


def load_runtime_limits(data: dict[str, Any]) -> RuntimeLimitsConfig:
    raw = cast(dict[str, Any], data.get("runtime_limits") or {})
    worker = cast(dict[str, Any], raw.get("worker") or {})
    poll = cast(dict[str, Any], raw.get("preview_poll") or {})
    llm = cast(dict[str, Any], raw.get("llm_request_timeout_seconds") or {})
    default_llm = int(llm.get("default") or 600)
    per_agent: dict[str, int] = {}
    for k, v in llm.items():
        if k == "default":
            continue
        if isinstance(v, (int, float)):
            per_agent[str(k)] = int(v)
    tts_timeout = int(worker.get("tts_subprocess_timeout_seconds") or 900)
    return RuntimeLimitsConfig(
        worker_man_render_timeout_seconds=int(worker.get("manim_render_timeout_seconds") or 3600),
        worker_tts_subprocess_timeout_seconds=tts_timeout,
        preview_poll_timeout_seconds=float(poll.get("timeout_seconds") or 900),
        preview_poll_interval_seconds=float(poll.get("interval_seconds") or 0.5),
        llm_timeout_default_seconds=default_llm,
        llm_timeouts=per_agent,
    )
