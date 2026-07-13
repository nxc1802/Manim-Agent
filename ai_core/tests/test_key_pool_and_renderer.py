from __future__ import annotations

import pytest
from app.llm import GoogleAPIKeyPool, KeyState
from app.renderer import UnsafeManimCode, validate_manim_code


def test_google_key_enters_cooldown_and_next_key_is_selected() -> None:
    pool = GoogleAPIKeyPool(["key-a", "key-b"])
    key, identity = pool.acquire()
    assert key == "key-a"
    pool.record_failure(identity, RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded"))
    next_key, _ = pool.acquire()
    assert next_key == "key-b"
    assert pool.snapshot()[0]["state"] == KeyState.COOLDOWN


def test_google_key_daily_quota_is_exhausted_until_next_day() -> None:
    pool = GoogleAPIKeyPool(["key-a"])
    _, identity = pool.acquire()
    pool.record_failure(identity, RuntimeError("RequestsPerDay quota exceeded"))
    assert pool.snapshot()[0]["state"] == KeyState.EXHAUSTED
    with pytest.raises(RuntimeError, match="No AVAILABLE"):
        pool.acquire()


def test_renderer_rejects_unsafe_import_before_subprocess() -> None:
    with pytest.raises(UnsafeManimCode, match="Import is not allowed"):
        validate_manim_code("import os\nfrom manim import Scene\n")
