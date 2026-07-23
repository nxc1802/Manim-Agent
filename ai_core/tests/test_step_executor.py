from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from app.errors import InactiveStepError
from app.step_executor import StepExecutor


class _StreamingLLM:
    async def stream(self, **_kwargs):  # noqa: ANN201
        yield "from manim import *\nclass GeneratedScene(Scene):\n    def construct(self):\n        pass"


class _StoryboardWithIdeaLLM:
    def __init__(self) -> None:
        self.idea_kwargs = None
        self.storyboard_kwargs = None

    def complete(self, **kwargs):  # noqa: ANN201
        self.idea_kwargs = kwargs
        return (
            '{"concept":"Fractions","audience":"Beginners",'
            '"learning_goal":"Compare fractions","key_points":["Common denominator",'
            '"Visual comparison"],"visual_metaphor":"Pie slices",'
            '"scope_notes":"Positive fractions only"}'
        )

    async def stream(self, **kwargs):  # noqa: ANN201
        self.storyboard_kwargs = kwargs
        yield (
            '{"scenes":[{"scene_order":1,"continuity":"new_section",'
            '"narration":"Compare fractions.","visual_action":"Draw two fraction bars."}]}'
        )


def _work_item() -> dict:
    return {
        "step": {"id": uuid4(), "kind": "builder", "input": {}},
        "project": {},
        "scene": {},
        "approved_outputs": [],
    }


def test_streaming_stops_when_backend_marks_step_inactive() -> None:
    executor = StepExecutor(llm=_StreamingLLM())  # type: ignore[arg-type]
    client = MagicMock()
    client.stream_step_chunk.side_effect = InactiveStepError("inactive")

    with pytest.raises(InactiveStepError, match="inactive"):
        executor.generate(_work_item(), backend_client=client)


def test_builder_stops_before_visual_review_when_code_review_is_exhausted() -> None:
    executor = StepExecutor(llm=_StreamingLLM())  # type: ignore[arg-type]
    code_result = {
        "passed": False,
        "manim_code": "broken code",
        "iterations": [],
        "total_attempts": 3,
        "final_error": "NameError: bad API",
    }
    executor._review_builder_code = MagicMock(return_value=code_result)  # type: ignore[method-assign]

    with patch("app.step_executor.BackendClient", return_value=MagicMock()):
        result = executor.generate(_work_item())

    assert executor._review_builder_code.call_count == 1
    assert result["auto_review"]["code"] == code_result
    assert "visual" not in result["auto_review"]
    assert result["auto_review"]["passed"] is False
    assert result["auto_review"]["final_error"] == "NameError: bad API"


def test_idea_and_storyboard_are_separate_durable_agent_calls() -> None:
    llm = _StoryboardWithIdeaLLM()
    executor = StepExecutor(llm=llm)  # type: ignore[arg-type]
    settings = {
        "llm_agent_configs": {
            "idea_sketcher": {"reasoning_effort": "high", "max_tokens": 4096},
            "storyboarder": {"reasoning_effort": "low", "max_tokens": 8192},
        }
    }
    idea_item = {
        "step": {"id": uuid4(), "kind": "idea_sketcher", "input": {"prompt": "Fractions"}},
        "project": {},
        "scene": None,
        "approved_outputs": [],
        "settings": settings,
    }

    with patch("app.step_executor.BackendClient", return_value=MagicMock()):
        idea = executor.generate(idea_item)
        result = executor.generate(
            {
                "step": {
                    "id": uuid4(),
                    "kind": "storyboarder",
                    "input": {"prompt": "Fractions"},
                },
                "project": {},
                "scene": None,
                "approved_outputs": [idea],
                "settings": settings,
            }
        )

    assert idea["concept"] == "Fractions"
    assert result["scenes"][0]["narration"] == "Compare fractions."
    assert llm.idea_kwargs["reasoning_effort"] == "high"
    assert llm.storyboard_kwargs["reasoning_effort"] == "low"
    storyboard_context = llm.storyboard_kwargs["messages"][1]["content"]
    assert '"concept": "Fractions"' in storyboard_context


def test_builder_runs_visual_review_only_after_code_review_passes() -> None:
    executor = StepExecutor(llm=_StreamingLLM())  # type: ignore[arg-type]
    code_result = {
        "passed": True,
        "manim_code": "valid code",
        "iterations": [],
        "total_attempts": 1,
        "final_error": None,
    }
    visual_result = {
        "passed": True,
        "manim_code": "visually reviewed code",
        "iterations": [],
        "total_attempts": 1,
        "final_error": None,
    }
    executor._review_builder_code = MagicMock(  # type: ignore[method-assign]
        side_effect=[code_result, visual_result]
    )

    with patch("app.step_executor.BackendClient", return_value=MagicMock()):
        result = executor.generate(_work_item())

    assert executor._review_builder_code.call_count == 2
    assert result["manim_code"] == "visually reviewed code"
    assert result["auto_review"]["passed"] is True


def test_review_loop_receives_the_user_attempt_limit() -> None:
    executor = StepExecutor(llm=MagicMock())
    work_item = _work_item()
    work_item["step"]["input"] = {"manim_code": "class GeneratedScene: pass"}
    work_item["settings"] = {"max_review_attempts": 2}
    loop = MagicMock()
    loop.run.return_value.model_dump.return_value = {
        "passed": True,
        "manim_code": "valid code",
        "iterations": [],
        "total_attempts": 1,
        "final_error": None,
    }

    with patch("app.step_executor.ReviewLoop", return_value=loop):
        result = executor._run_review_loop(work_item, config=MagicMock(), client=MagicMock())

    assert loop.run.call_args.kwargs["max_attempts"] == 2
    assert result["attempt_config"]["max_review_attempts"] == 2


def test_reviewer_reuses_the_task_backend_client_for_stage_callbacks() -> None:
    executor = StepExecutor(llm=MagicMock())
    work_item = _work_item()
    work_item["step"]["kind"] = "code_reviewer"
    work_item["step"]["input"] = {"manim_code": "class GeneratedScene: pass"}
    backend_client = MagicMock()
    loop = MagicMock()
    loop.run.return_value.model_dump.return_value = {
        "passed": True,
        "manim_code": "valid code",
        "iterations": [],
        "total_attempts": 1,
        "final_error": None,
    }

    with (
        patch("app.step_executor.BackendClient") as backend_client_type,
        patch("app.step_executor.ReviewLoop", return_value=loop),
    ):
        executor.generate(work_item, backend_client=backend_client)

    loop.run.call_args.kwargs["on_stage"]({"status": "reviewing"})
    backend_client.publish_step_stage.assert_called_once_with(
        work_item["step"]["id"], {"status": "reviewing"}
    )
    backend_client_type.assert_not_called()


def test_generation_model_overrides_are_applied_without_changing_defaults() -> None:
    default = StepExecutor._effective_model_config("builder", {})
    overridden = StepExecutor._effective_model_config(
        "builder",
        {
            "llm_model": "gemini-3.5-flash",
            "llm_temperature": 0.7,
            "llm_max_tokens": 4096,
        },
    )

    assert default.model == "gemini-3.6-flash"
    assert default.temperature == 0.1
    assert overridden.model == "gemini-3.5-flash"
    assert overridden.temperature == 0.7
    assert overridden.max_tokens == 4096


def test_agent_specific_model_override_wins_over_legacy_global_override() -> None:
    configured = StepExecutor._effective_model_config(
        "builder",
        {
            "llm_model": "gemma-4-31b-it",
            "llm_temperature": 0.7,
            "llm_agent_configs": {
                "builder": {
                    "model": "gemini-3.5-flash",
                    "temperature": 0.1,
                    "max_tokens": 8192,
                }
            },
        },
    )

    assert configured.model == "gemini-3.5-flash"
    assert configured.temperature == 0.1
    assert configured.max_tokens == 8192


def test_custom_code_reviewer_chain_replaces_the_backend_default_chain() -> None:
    executor = StepExecutor(llm=MagicMock())
    work_item = _work_item()
    work_item["step"]["input"] = {"manim_code": "class GeneratedScene: pass"}
    work_item["settings"] = {
        "max_review_attempts": 2,
        "llm_agent_configs": {
            "code_reviewer": {
                "temperature": 0.7,
                "review_tiers": [
                    {"model": "gemini-3.5-flash", "max_attempts": 2, "reasoning_effort": "high"},
                    {"model": "gemini-3.5-flash-lite", "max_attempts": 1, "reasoning_effort": "low"},
                ],
            }
        },
    }
    loop = MagicMock()
    loop.run.return_value.model_dump.return_value = {
        "passed": True,
        "manim_code": "valid code",
        "iterations": [],
        "total_attempts": 1,
        "final_error": None,
    }

    with patch("app.step_executor.ReviewLoop", return_value=loop) as review_loop:
        result = executor._run_review_loop(
            work_item, config=MagicMock(uses_vision=False), client=MagicMock()
        )

    selected_tiers = review_loop.call_args.kwargs["tiers"]
    assert [(tier.model, tier.max_attempts) for tier in selected_tiers] == [
        ("gemini-3.5-flash", 2),
        ("gemini-3.5-flash-lite", 1),
    ]
    assert [tier.reasoning_effort for tier in selected_tiers] == ["high", "low"]
    assert loop.run.call_args.kwargs["llm_config"].temperature == 0.7
    assert result["attempt_config"] == {
        "max_review_attempts": 2,
        "tiers": [
            {"model": "gemini-3.5-flash", "max_attempts": 2, "reasoning_effort": "high"},
            {"model": "gemini-3.5-flash-lite", "max_attempts": 1, "reasoning_effort": "low"},
        ],
    }


def test_reviewer_without_custom_chain_keeps_backend_escalation() -> None:
    executor = StepExecutor(llm=MagicMock())
    work_item = _work_item()
    work_item["step"]["input"] = {"manim_code": "class GeneratedScene: pass"}
    work_item["settings"] = {"llm_agent_configs": {"code_reviewer": {"model": "gemini-3.5-flash"}}}
    loop = MagicMock()
    loop.run.return_value.model_dump.return_value = {
        "passed": True,
        "manim_code": "valid code",
        "iterations": [],
        "total_attempts": 1,
        "final_error": None,
    }

    with patch("app.step_executor.ReviewLoop", return_value=loop) as review_loop:
        executor._run_review_loop(work_item, config=MagicMock(uses_vision=False), client=MagicMock())

    assert review_loop.call_args.kwargs["tiers"] is None
