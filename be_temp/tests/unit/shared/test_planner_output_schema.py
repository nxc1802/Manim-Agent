from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError
from shared.schemas.planner_output import PlannerOutput


def _fixture(name: str) -> dict[str, object]:
    path = Path(__file__).resolve().parents[2] / "fixtures" / name
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def test_planner_output_valid_fixture() -> None:
    data = _fixture("planner_output_valid.json")
    plan = PlannerOutput.model_validate(data)
    assert plan.version == "1"
    assert len(plan.beats) == 2
    assert plan.beats[0].step_label == "intro"
    assert plan.beats[0].primitives[0].name == "title_card"


def test_planner_output_invalid_empty_beats() -> None:
    data = _fixture("planner_output_invalid.json")
    with pytest.raises(ValidationError):
        PlannerOutput.model_validate(data)
