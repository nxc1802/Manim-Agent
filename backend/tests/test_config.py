from app.core.config import Settings


def test_agent_step_stale_timeout_defaults_to_three_minutes(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("AI_STEP_STALE_AFTER_SECONDS", raising=False)

    assert Settings(_env_file=None).ai_step_stale_after_seconds == 180
