from __future__ import annotations

from pathlib import Path

PROMPT_VERSION_DIRECTOR = "2026-04-24-director-v2"
PROMPT_VERSION_PLANNER = "2026-04-24-planner-v2"
PROMPT_VERSION_BUILDER = "2026-04-24-builder-v2"
PROMPT_VERSION_CODE_REVIEWER = "2026-04-24-code-reviewer-v2"
PROMPT_VERSION_VISUAL_REVIEWER = "2026-04-24-visual-reviewer-v2"


def _prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


def load_prompt_text(filename: str) -> str:
    path = _prompts_dir() / filename
    return path.read_text(encoding="utf-8")
