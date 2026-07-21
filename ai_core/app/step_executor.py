from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import nullcontext
from typing import Any

from app.backend_client import BackendClient
from app.llm import GoogleLLM
from app.models import AgentModel, ModelTier, load_agent_model, load_review_loop_tiers
from app.prompts import SYSTEM_PROMPTS
from app.review_loop import CODE_REVIEW_CONFIG, VISUAL_REVIEW_CONFIG, ReviewLoop

logger = logging.getLogger(__name__)


class StepExecutor:
    def __init__(self, llm: GoogleLLM | None = None) -> None:
        self.llm = llm or GoogleLLM()

    def generate(
        self,
        work_item: dict[str, Any],
        backend_client: BackendClient | None = None,
    ) -> dict[str, Any]:
        raw_step = work_item["step"]
        kind = str(raw_step["kind"])

        # code_reviewer and visual_reviewer use the ReviewLoop engine
        if kind == "code_reviewer":
            return self._run_review_loop(work_item, CODE_REVIEW_CONFIG, backend_client)
        if kind == "visual_reviewer":
            return self._run_review_loop(work_item, VISUAL_REVIEW_CONFIG, backend_client)

        # Idea sketch, storyboard and builder are durable public stages.
        config = self._effective_model_config(kind, work_item.get("settings") or {})
        context = {
            "input": raw_step.get("input", {}),
            "project": work_item.get("project", {}),
            "scene": work_item.get("scene", {}),
            "approved_outputs": work_item.get("approved_outputs", []),
        }
        if kind == "idea_sketcher":
            return self._generate_idea_blueprint(
                context,
                work_item.get("settings") or {},
            )
        client_scope = (
            nullcontext(backend_client) if backend_client is not None else BackendClient()
        )
        with client_scope as client:
            return self._generate_with_client(
                work_item=work_item,
                raw_step=raw_step,
                kind=kind,
                config=config,
                context=context,
                client=client,
            )

    def _generate_with_client(
        self,
        *,
        work_item: dict[str, Any],
        raw_step: dict[str, Any],
        kind: str,
        config: AgentModel,
        context: dict[str, Any],
        client: BackendClient,
    ) -> dict[str, Any]:
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
                reasoning_effort=config.reasoning_effort,
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
            except json.JSONDecodeError as exc:
                logger.error("Failed to parse %s JSON: %s", kind, json_text)
                raise ValueError(f"{kind} returned invalid JSON") from exc
            scenes = data.get("scenes") if isinstance(data, dict) else None
            if not isinstance(scenes, list) or not scenes or not all(
                isinstance(scene, dict) for scene in scenes
            ):
                raise ValueError("Storyboarder must return a non-empty scenes array")
            return {"scenes": scenes}

        if kind == "builder":
            code = re.sub(r"^```(?:python)?\s*|\s*```$", "", text).strip()

            settings = work_item.get("settings") or {}
            code_review_enabled = settings.get("code_review_enabled", True)
            visual_review_enabled = settings.get("visual_review_enabled", True)

            auto_review: dict[str, Any] = {}
            try:
                if code_review_enabled:
                    auto_review["code"] = self._review_builder_code(
                        code, work_item, CODE_REVIEW_CONFIG, client
                    )
                    code = auto_review["code"]["manim_code"]
                    if not auto_review["code"].get("passed"):
                        auto_review["passed"] = False
                        auto_review["final_error"] = auto_review["code"].get("final_error")
                        logger.warning(
                            "Builder code review exhausted without a valid render: %s",
                            auto_review["final_error"],
                        )
                        return {"manim_code": code, "auto_review": auto_review}
                else:
                    auto_review["code"] = {"passed": True, "manim_code": code, "skipped": True}

                if visual_review_enabled:
                    # Visual review is meaningful only after code review produced a
                    # valid render. It uses the same partial-patch and audit engine.
                    auto_review["visual"] = self._review_builder_code(
                        code, work_item, VISUAL_REVIEW_CONFIG, client
                    )
                    code = auto_review["visual"]["manim_code"]
                    auto_review["passed"] = bool(auto_review["visual"].get("passed"))
                    if not auto_review["passed"]:
                        auto_review["final_error"] = auto_review["visual"].get("final_error")
                else:
                    auto_review["visual"] = {"passed": True, "manim_code": code, "skipped": True}
                    auto_review["passed"] = True
            except Exception as exc:  # noqa: BLE001
                logger.exception("Builder auto-review failed unexpectedly")
                auto_review["error"] = str(exc)
                auto_review["passed"] = False
                auto_review["final_error"] = str(exc)
            return {"manim_code": code, "auto_review": auto_review}

        return {"text": text}

    def _generate_idea_blueprint(
        self,
        storyboard_context: dict[str, Any],
        user_settings: dict[str, Any],
    ) -> dict[str, Any]:
        """Run the lightweight idea agent before the agentic Master call."""
        config = self._effective_model_config("idea_sketcher", user_settings)
        raw = self.llm.complete(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPTS["idea_sketcher"]},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "input": storyboard_context.get("input", {}),
                            "project": storyboard_context.get("project", {}),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            reasoning_effort=config.reasoning_effort,
        )
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
        json_text = json_match.group(1) if json_match else raw
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise ValueError("Idea sketcher returned invalid JSON") from exc
        required_strings = (
            "concept",
            "audience",
            "learning_goal",
            "visual_metaphor",
            "scope_notes",
        )
        if not isinstance(data, dict) or any(
            not isinstance(data.get(field), str) or not data[field].strip()
            for field in required_strings
        ):
            raise ValueError("Idea sketcher returned an incomplete blueprint")
        key_points = data.get("key_points")
        if (
            not isinstance(key_points, list)
            or not 2 <= len(key_points) <= 6
            or not all(isinstance(item, str) and item.strip() for item in key_points)
        ):
            raise ValueError("Idea sketcher key_points must contain 2 to 6 strings")
        return {
            **{field: data[field].strip() for field in required_strings},
            "key_points": [item.strip() for item in key_points],
        }

    @staticmethod
    def _effective_model_config(kind: str, user_settings: dict[str, Any]) -> AgentModel:
        """Apply the persisted LLM overrides without replacing agent defaults.

        A missing override intentionally keeps the values from
        ``agent_models.yaml``: storyboard generation and Manim building have
        different safe defaults.
        """
        configured = load_agent_model(kind)
        agent_configs = user_settings.get("llm_agent_configs")
        agent_override = (
            agent_configs.get(kind, {}) if isinstance(agent_configs, dict) else {}
        )
        if not isinstance(agent_override, dict):
            agent_override = {}
        return AgentModel(
            model=str(
                agent_override.get("model")
                or user_settings.get("llm_model")
                or configured.model
            ),
            temperature=float(
                agent_override.get("temperature")
                if agent_override.get("temperature") is not None
                else (
                    configured.temperature
                    if user_settings.get("llm_temperature") is None
                    else user_settings["llm_temperature"]
                )
            ),
            max_tokens=int(
                agent_override.get("max_tokens")
                if agent_override.get("max_tokens") is not None
                else (
                    configured.max_tokens
                    if user_settings.get("llm_max_tokens") is None
                    else user_settings["llm_max_tokens"]
                )
            ),
            reasoning_effort=str(
                agent_override.get("reasoning_effort")
                or configured.reasoning_effort
            ),
        )

    def _review_builder_code(
        self, code: str, work_item: dict[str, Any], config: Any, client: BackendClient
    ) -> dict[str, Any]:
        """Run an internal reviewer without mutating the original work item."""
        review_item = dict(work_item)
        step = dict(work_item["step"])
        step["input"] = {**step.get("input", {}), "manim_code": code}
        review_item["step"] = step
        return self._run_review_loop(review_item, config, client)

    def _run_review_loop(
        self,
        work_item: dict[str, Any],
        config: Any,
        client: BackendClient | None = None,
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
        configured_attempts = (work_item.get("settings") or {}).get("max_review_attempts")
        max_attempts = (
            configured_attempts
            if isinstance(configured_attempts, int) and not isinstance(configured_attempts, bool)
            else None
        )
        user_settings = work_item.get("settings") or {}
        agent_kind = "visual_reviewer" if config.uses_vision else "code_reviewer"
        llm_config = self._effective_model_config(agent_kind, user_settings)
        agent_configs = user_settings.get("llm_agent_configs")
        configured_agent = agent_configs.get(agent_kind, {}) if isinstance(agent_configs, dict) else {}
        custom_tiers = (
            configured_agent.get("review_tiers") if isinstance(configured_agent, dict) else None
        )
        loop = ReviewLoop(
            llm=self.llm,
            tiers=self._review_tiers(custom_tiers) if custom_tiers is not None else None,
        )
        step_id = work_item["step"]["id"]
        client_scope = nullcontext(client) if client is not None else BackendClient()
        with client_scope as active_client:
            result = loop.run(
                code,
                config=config,
                context=work_item,
                on_stage=lambda stage: active_client.publish_step_stage(step_id, stage),
                max_attempts=max_attempts,
                llm_config=llm_config,
            )
        logger.info(
            "Review loop (%s) completed: passed=%s, attempts=%d, iterations=%d",
            "visual" if config.uses_vision else "code",
            result.passed,
            result.total_attempts,
            len(result.iterations),
        )
        return result.model_dump()

    @staticmethod
    def _review_tiers(value: object) -> list[ModelTier]:
        """Convert a persisted reviewer chain into ordered runtime tiers.

        ``None`` is handled by the caller as “use backend default”. An invalid
        or empty custom list is rejected before this point by the user settings
        schema; this guard protects workers consuming old/corrupt snapshots.
        """
        if not isinstance(value, list) or not value:
            return load_review_loop_tiers()
        allowed_models = {tier.model for tier in load_review_loop_tiers()}
        tiers: list[ModelTier] = []
        seen_models: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                continue
            model = item.get("model")
            attempts = item.get("max_attempts")
            if (
                not isinstance(model, str)
                or model not in allowed_models
                or model in seen_models
                or not isinstance(attempts, int)
                or isinstance(attempts, bool)
                or not 1 <= attempts <= 5
            ):
                continue
            reasoning_effort = item.get("reasoning_effort", "none")
            if reasoning_effort not in {"none", "minimal", "low", "medium", "high"}:
                reasoning_effort = "none"
            tiers.append(
                ModelTier(
                    model=model,
                    max_attempts=attempts,
                    reasoning_effort=str(reasoning_effort),
                )
            )
            seen_models.add(model)
        return tiers or load_review_loop_tiers()
