from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.backend_client import BackendClient
from app.llm import GoogleLLM
from app.models import load_agent_model
from app.prompts import SYSTEM_PROMPTS
from app.review_loop import CODE_REVIEW_CONFIG, VISUAL_REVIEW_CONFIG, ReviewLoop

logger = logging.getLogger(__name__)


class StepExecutor:
    def __init__(self, llm: GoogleLLM | None = None) -> None:
        self.llm = llm or GoogleLLM()

    def generate(self, work_item: dict[str, Any]) -> dict[str, Any]:
        raw_step = work_item["step"]
        kind = str(raw_step["kind"])

        # code_reviewer and visual_reviewer use the ReviewLoop engine
        if kind == "code_reviewer":
            return self._run_review_loop(work_item, CODE_REVIEW_CONFIG)
        if kind == "visual_reviewer":
            return self._run_review_loop(work_item, VISUAL_REVIEW_CONFIG)

        # Regular agent steps: director, planner, scene_designer, builder
        config = load_agent_model(kind)
        context = {
            "input": raw_step.get("input", {}),
            "project": work_item.get("project", {}),
            "scene": work_item.get("scene", {}),
            "approved_outputs": work_item.get("approved_outputs", []),
        }
        client = BackendClient()
        step_id = raw_step["id"]

        async def _stream_generate() -> str:
            full_text = ""
            async for chunk in self.llm.stream(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPTS[kind]},
                    {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
                ],
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            ):
                full_text += chunk
                try:
                    client.stream_step_chunk(step_id, chunk)
                except Exception as exc:
                    logger.warning("Failed to stream chunk: %s", exc)
            return full_text

        text = asyncio.run(_stream_generate()).strip()
        if kind == "storyboarder":
            # Extract JSON block
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
            json_text = json_match.group(1) if json_match else text
            try:
                data = json.loads(json_text)
                return {"scenes": data.get("scenes", [])}
            except json.JSONDecodeError:
                logger.error("Failed to parse storyboarder JSON: %s", json_text)
                return {"scenes": []}
                
        if kind == "builder":
            code = re.sub(r"^```(?:python)?\s*|\s*```$", "", text).strip()
            # Perform internal dry-run
            from app.renderer import render_manim_for_validation
            import shutil
            
            try:
                val_result = render_manim_for_validation(code, extra_flags=["-s"])
                if val_result.temp_dir:
                    shutil.rmtree(val_result.temp_dir, ignore_errors=True)
                
                if not val_result.success:
                    logger.info("Builder dry-run failed. Invoking internal code_reviewer fallback.")
                    # Re-package for internal review loop
                    fallback_work_item = dict(work_item)
                    fallback_work_item["step"]["input"]["manim_code"] = code
                    return self._run_review_loop(fallback_work_item, CODE_REVIEW_CONFIG)
            except Exception as e:
                logger.warning("Dry-run check threw exception: %s", e)
                
            return {"manim_code": code}
            
        return {"text": text}

    def _run_review_loop(
        self,
        work_item: dict[str, Any],
        config: Any,
    ) -> dict[str, Any]:
        """Run unified review loop (identical for code_reviewer and visual_reviewer).

        The ONLY difference is ``config`` (prompts + render flags).
        """
        step_input = work_item["step"].get("input", {})
        scene = work_item.get("scene", {})
        # manim_code: injected by Backend _queue_next, fallback to scene.manim_code
        code = step_input.get("manim_code") or scene.get("manim_code", "")
        if not code:
            return {
                "passed": False,
                "manim_code": "",
                "iterations": [],
                "total_attempts": 0,
                "final_error": "No manim_code available for review",
            }
        loop = ReviewLoop(llm=self.llm)
        result = loop.run(code, config=config, context=work_item)
        logger.info(
            "Review loop (%s) completed: passed=%s, attempts=%d, iterations=%d",
            "visual" if config.uses_vision else "code",
            result.passed,
            result.total_attempts,
            len(result.iterations),
        )
        return result.model_dump()
