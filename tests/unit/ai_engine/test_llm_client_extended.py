from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from ai_engine.llm_client import LiteLLMClient


@pytest.fixture
def client() -> LiteLLMClient:
    return LiteLLMClient(api_key="sk-test", provider_keys={"dashscope": "ds-test"})


def test_litellm_get_completion_kwargs_dashscope(client: LiteLLMClient) -> None:
    kwargs = client._get_completion_kwargs(
        model="dashscope/qwen-max",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.7,
        max_tokens=100,
        json_mode=True,
        timeout=60.0,
    )
    assert kwargs["api_key"] == "ds-test"
    assert "compatible-mode" in kwargs["api_base"]
    assert kwargs["response_format"] == {"type": "json_object"}


def test_litellm_get_completion_kwargs_ollama(client: LiteLLMClient) -> None:
    client._api_base = "http://localhost:11434"
    kwargs = client._get_completion_kwargs(
        model="llama3",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.7,
        max_tokens=100,
        json_mode=False,
        timeout=60.0,
    )
    assert kwargs["extra_body"]["num_ctx"] == 16384


def test_litellm_get_completion_kwargs_reasoning(client: LiteLLMClient) -> None:
    kwargs = client._get_completion_kwargs(
        model="openrouter/deepseek-reasoning",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.7,
        max_tokens=100,
        json_mode=False,
        timeout=60.0,
    )
    assert kwargs["extra_body"]["reasoning"]["enabled"] is True


@patch("litellm.completion")
def test_litellm_complete_ex_success(mock_completion: MagicMock, client: LiteLLMClient) -> None:
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "hello world"
    mock_resp.usage.prompt_tokens = 10
    mock_resp.usage.completion_tokens = 5
    mock_completion.return_value = mock_resp

    res = client.complete_ex(
        model="gpt-3.5-turbo",
        system="sys",
        user="usr",
        json_mode=False,
        temperature=0.7,
        max_tokens=100,
        request_timeout_seconds=30,
    )
    assert res.text == "hello world"
    assert res.usage.prompt_tokens == 10


@patch("litellm.completion")
def test_litellm_complete_with_images_ex_success(mock_completion: MagicMock, client: LiteLLMClient) -> None:
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "image description"
    mock_completion.return_value = mock_resp

    res = client.complete_with_images_ex(
        model="gpt-4-vision",
        system="sys",
        user="usr",
        image_jpeg=b"fake-image",
        json_mode=False,
        temperature=0.7,
        max_tokens=100,
        request_timeout_seconds=30,
    )
    assert res.text == "image description"


@pytest.mark.anyio
@patch("litellm.acompletion")
async def test_litellm_acomplete_chat_ex_success(mock_acompletion: MagicMock, client: LiteLLMClient) -> None:
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "async hello"
    mock_resp.usage = None
    mock_acompletion.return_value = mock_resp

    res = await client.acomplete_chat_ex(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "hi"}],
        json_mode=False,
        temperature=0.7,
        max_tokens=100,
        request_timeout_seconds=30,
    )
    assert res.text == "async hello"
