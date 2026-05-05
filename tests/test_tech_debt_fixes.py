import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from ai_engine.config import resolve_agent_params
from ai_engine.orchestrator import truncate_error_logs
from ai_engine.prompts import render_prompt


def test_sandwich_truncation():
    logs = "A" * 1000 + "MIDDLE" + "B" * 1000
    truncated = truncate_error_logs(logs, max_chars=500)
    print(f"Original length: {len(logs)}")
    print(f"Truncated length: {len(truncated)}")
    print(f"Truncated content snippet: {truncated[:50]}...{truncated[-50:]}")
    assert "... [TRUNCATED] ..." in truncated
    assert len(truncated) <= 510  # approx
    assert truncated.startswith("A" * 100)
    assert truncated.endswith("B" * 100)
    print("✓ Sandwich truncation verified")


def test_jinja_rendering():
    # Create a temporary prompt file
    prompt_dir = Path("ai_engine/prompts")
    prompt_dir.mkdir(parents=True, exist_ok=True)
    test_prompt = prompt_dir / "test_jinja.txt"
    test_prompt.write_text("Hello {{ name }}! Version: {{ version }}", encoding="utf-8")

    try:
        rendered = render_prompt("test_jinja.txt", {"name": "Antigravity", "version": "v1"})
        print(f"Rendered: {rendered}")
        assert rendered == "Hello Antigravity! Version: v1"
        print("✓ Jinja2 rendering verified")
    finally:
        test_prompt.unlink()


def test_config_fallback():
    # Set env var
    os.environ["DEFAULT_AGENT_MODEL"] = "test/dummy-model"
    # Need to re-instantiate settings or check if it picks up env
    from backend.core.config import Settings

    new_settings = Settings()
    print(f"Default model from settings: {new_settings.default_agent_model}")
    assert new_settings.default_agent_model == "test/dummy-model"

    # Check resolve_agent_params (mocking settings in ai_engine.config might be needed
    # if it's already imported)
    # But since we changed the code to use 'settings.default_agent_model',
    # it should work if we monkeypatch it or if it re-evaluates.
    import ai_engine.config

    ai_engine.config.settings = new_settings
    params = resolve_agent_params({}, "builder")
    print(f"Resolved model: {params.model}")
    assert params.model == "test/dummy-model"
    print("✓ Config fallback verified")


if __name__ == "__main__":
    try:
        test_sandwich_truncation()
        test_jinja_rendering()
        test_config_fallback()
        print("\nALL TESTS PASSED!")
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        sys.exit(1)
