from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ai_engine.agents.repair import run_repair
from ai_engine.llm_client import LLMCompletion, LLMUsage
from shared.constants import SeverityLevel
from shared.schemas.validation import ValidationIssue


@pytest.mark.anyio
async def test_run_repair_success() -> None:
    mock_llm = MagicMock()

    repaired_code_response = """
Here is the repaired code:
```python
from manim import *
class GeneratedScene(Scene):
    def construct(self):
        self.play(Write(Text("Fixed")))
```
"""
    mock_completion = LLMCompletion(
        text=repaired_code_response,
        usage=LLMUsage(prompt_tokens=10, completion_tokens=20, duration_ms=100),
    )

    async def mock_acomplete_ex(**kwargs: any) -> LLMCompletion:
        return mock_completion

    mock_llm.acomplete_ex = mock_acomplete_ex

    errors = [
        ValidationIssue(
            code="tex_usage",
            severity=SeverityLevel.ERROR,
            message="Tex usage is forbidden",
            line=10,
        )
    ]

    code, pv, met, sys_p, usr_p = await run_repair(
        llm=mock_llm,
        model="test-model",
        temperature=0.1,
        max_tokens=1000,
        original_code="original code here",
        validation_errors=errors,
    )

    assert "class GeneratedScene(Scene):" in code
    assert 'Write(Text("Fixed"))' in code
    assert "tex_usage" in usr_p
    assert "original code here" in usr_p
