from __future__ import annotations

from pathlib import Path
from typing import Any

import jinja2

PROMPT_VERSION_DIRECTOR = "2026-04-24-director-v2"
PROMPT_VERSION_PLANNER = "2026-04-24-planner-v2"
PROMPT_VERSION_BUILDER = "2026-04-24-builder-v2"
PROMPT_VERSION_CODE_REVIEWER = "2026-04-24-code-reviewer-v2"
PROMPT_VERSION_VISUAL_REVIEWER = "2026-04-24-visual-reviewer-v2"


def _prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


_JINJA_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_prompts_dir())),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


def load_prompt_text(filename: str) -> str:
    path = _prompts_dir() / filename
    return path.read_text(encoding="utf-8")


def render_prompt(filename: str, context: dict[str, Any] | None = None) -> str:
    """Load a prompt template from file and render it using Jinja2."""
    template = _JINJA_ENV.get_template(filename)
    return template.render(context or {})
