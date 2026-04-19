"""E2E fixtures: real LLM gate (see CONTRIBUTING.md)."""

from __future__ import annotations

import os

import pytest


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


@pytest.fixture(scope="module")
def e2e_llm_gate() -> None:
    """Require E2E_LLM=1 plus OPENROUTER_API_KEY; fail on CI if the key is missing."""
    if not _truthy("E2E_LLM"):
        pytest.skip("Set E2E_LLM=1 to run tests/e2e (see CONTRIBUTING.md)")
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        if (os.environ.get("CI") or "").lower() == "true":
            pytest.fail("CI: OPENROUTER_API_KEY is required when E2E_LLM=1 (add repo secret)")
        pytest.skip("OPENROUTER_API_KEY not set; export your OpenRouter key for LiteLLM")
