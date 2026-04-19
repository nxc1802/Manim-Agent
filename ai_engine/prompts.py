from __future__ import annotations

from pathlib import Path

PROMPT_VERSION_DIRECTOR = "2026-04-18-director-v1"
PROMPT_VERSION_PLANNER = "2026-04-18-planner-v1"
PROMPT_VERSION_BUILDER = "2026-04-18-builder-v1"
PROMPT_VERSION_SYNC_ENGINE = "2026-04-18-sync-engine-v1"
PROMPT_VERSION_CODE_REVIEWER = "2026-04-18-code-reviewer-v1"
PROMPT_VERSION_VISUAL_REVIEWER = "2026-04-18-visual-reviewer-v1"


def _prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


def load_prompt_text(filename: str) -> str:
    path = _prompts_dir() / filename
    return path.read_text(encoding="utf-8")
