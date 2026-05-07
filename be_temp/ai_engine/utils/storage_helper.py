from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from backend.core.config import settings


def save_agent_interaction(
    project_id: UUID | str,
    agent_name: str,
    phase_name: str,
    system_prompt: str,
    user_prompt: str,
    output: Any,
    round_idx: int | None = None,
) -> None:
    """
    Saves agent prompts and responses to storage/outputs/{project_id}/prompts_responses/
    """
    try:
        base_dir = Path(settings.output_dir) / str(project_id) / "prompts_responses" / agent_name
        base_dir.mkdir(parents=True, exist_ok=True)

        prefix = phase_name
        if round_idx is not None:
            prefix = f"round_{round_idx}_{phase_name}"

        # 1. Save System Prompt (Final version used)
        (base_dir / f"{prefix}_system.txt").write_text(system_prompt, encoding="utf-8")

        # 2. Save User Prompt
        (base_dir / f"{prefix}_user.txt").write_text(user_prompt, encoding="utf-8")

        # 3. Save Output (Raw response)
        if isinstance(output, (dict, list)):
            content = json.dumps(output, indent=2, ensure_ascii=False)
            ext = "json"
        elif hasattr(output, "model_dump_json"):
            content = output.model_dump_json(indent=2)
            ext = "json"
        else:
            content = str(output)
            ext = "txt"

        (base_dir / f"{prefix}_output.{ext}").write_text(content, encoding="utf-8")

    except Exception as e:
        import logging

        logging.getLogger("ai_engine.storage").warning(f"Failed to save agent interaction: {e}")
