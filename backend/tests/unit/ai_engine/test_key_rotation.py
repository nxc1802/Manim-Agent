from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from ai_engine.llm_client import KeyRotator, LiteLLMClient


def test_key_rotator_basic() -> None:
    rotator = KeyRotator(["key1", "key2", "key3"])
    assert rotator.get_next_key() == "key1"
    assert rotator.get_next_key() == "key2"
    assert rotator.get_next_key() == "key3"
    assert rotator.get_next_key() == "key1"  # loops around


def test_key_rotator_env_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_ROTATION_KEY", "secret_value")
    rotator = KeyRotator(["${TEST_ROTATION_KEY}"])
    assert rotator.get_next_key() == "secret_value"


@patch("litellm.completion")
def test_litellm_client_key_rotation(mock_completion: MagicMock) -> None:
    # Set up mock response
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "mocked response"
    mock_resp.usage = None
    mock_completion.return_value = mock_resp

    # Initialize client with mock config data override
    client = LiteLLMClient(api_key="sk-default")

    # Configure mock agent models data directly to avoid loading real agent_models.yaml
    client._config_data = {
        "providers": {
            "google_ai_studio": {
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
                "keys": ["key-A", "key-B"],
            }
        },
        "agents": {"director": {"provider": "google_ai_studio"}},
    }
    # Initialize rotators from mock config data
    client._rotators = {"google_ai_studio": KeyRotator(["key-A", "key-B"])}

    # First call for agent 'director'
    client.complete_ex(
        model="gemini-2.5-flash",
        system="sys",
        user="usr",
        json_mode=False,
        temperature=0.7,
        max_tokens=100,
        request_timeout_seconds=30,
        agent_name="director",
    )
    # Check that completion was called with the first key
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["api_key"] == "key-A"
    assert call_kwargs["api_base"] == "https://generativelanguage.googleapis.com/v1beta/openai/"

    # Second call for agent 'director'
    client.complete_ex(
        model="gemini-2.5-flash",
        system="sys",
        user="usr",
        json_mode=False,
        temperature=0.7,
        max_tokens=100,
        request_timeout_seconds=30,
        agent_name="director",
    )
    # Check that completion was called with the second key
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["api_key"] == "key-B"


def test_litellm_client_google_env_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    # Method 1: Comma-separated env loading
    monkeypatch.setenv("GOOGLE_API_KEY", "env-key-1, env-key-2")
    client = LiteLLMClient(api_key="sk-default")
    # Verify that the google_ai_studio rotator is set up with these keys
    assert "google_ai_studio" in client._rotators
    rotator = client._rotators["google_ai_studio"]
    assert rotator.get_next_key() == "env-key-1"
    assert rotator.get_next_key() == "env-key-2"
    assert rotator.get_next_key() == "env-key-1"


def test_litellm_client_google_env_suffixes(monkeypatch: pytest.MonkeyPatch) -> None:
    # Method 2: Key suffix env loading (when GOOGLE_API_KEY is not present)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY_1", "suffix-key-1")
    monkeypatch.setenv("GOOGLE_API_KEY_2", "suffix-key-2")
    client = LiteLLMClient(api_key="sk-default")
    assert "google_ai_studio" in client._rotators
    rotator = client._rotators["google_ai_studio"]
    assert rotator.get_next_key() == "suffix-key-1"
    assert rotator.get_next_key() == "suffix-key-2"
    assert rotator.get_next_key() == "suffix-key-1"
