"""E2E fixtures: optional live OpenRouter (see CONTRIBUTING.md)."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="module")
def e2e_openrouter_gate() -> None:
    """Run live-LLM E2E only when OPENROUTER_API_KEY is set; otherwise skip (CI stays green)."""
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        pytest.skip("OPENROUTER_API_KEY not set; skipping live LLM E2E")
