from __future__ import annotations

import base64
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable, cast

logger = logging.getLogger(__name__)


class KeyRotator:
    def __init__(self, keys: list[str]):
        self._keys = keys
        self._index = 0
        self._lock = threading.Lock()

    def get_next_key(self) -> str:
        if not self._keys:
            return ""
        with self._lock:
            key = self._keys[self._index]
            self._index = (self._index + 1) % len(self._keys)
            # Resolve env vars like ${KEY} dynamically
            match = re.match(r"\$\{(.+)\}", key)
            if match:
                return os.environ.get(match.group(1), "")
            return key


@dataclass(frozen=True)
class LLMUsage:
    bytes: None = None  # Add placeholder to avoid signature changes if any
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    duration_ms: int = 0


# Keep structural fields matching existing constructor
@dataclass(frozen=True)
class LLMCompletion:
    text: str
    usage: LLMUsage


@runtime_checkable
class SyncLLMClient(Protocol):
    def complete_ex(
        self,
        *,
        model: str,
        system: str,
        user: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
        agent_name: str | None = None,
    ) -> LLMCompletion: ...

    def complete_chat_ex(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
        agent_name: str | None = None,
    ) -> LLMCompletion: ...

    def complete_with_images_ex(
        self,
        *,
        model: str,
        system: str,
        user: str,
        image_jpeg: bytes,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
        agent_name: str | None = None,
    ) -> LLMCompletion: ...


@runtime_checkable
class AsyncLLMClient(Protocol):
    async def acomplete_ex(
        self,
        *,
        model: str,
        system: str,
        user: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
        agent_name: str | None = None,
    ) -> LLMCompletion: ...

    async def acomplete_chat_ex(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
        agent_name: str | None = None,
    ) -> LLMCompletion: ...

    async def acomplete_with_images_ex(
        self,
        *,
        model: str,
        system: str,
        user: str,
        image_jpeg: bytes,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
        agent_name: str | None = None,
    ) -> LLMCompletion: ...


# Backward-compatible union
LLMClient = SyncLLMClient | AsyncLLMClient


class LLMClientMixin:
    """Provides standard convenience methods calling the _ex variants."""

    def complete(
        self,
        *,
        model: str,
        system: str,
        user: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        agent_name: str | None = None,
    ) -> str:
        return cast(SyncLLMClient, self).complete_ex(
            model=model,
            system=system,
            user=user,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout_seconds=None,
            agent_name=agent_name,
        ).text

    def complete_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        agent_name: str | None = None,
    ) -> str:
        return cast(SyncLLMClient, self).complete_chat_ex(
            model=model,
            messages=messages,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout_seconds=None,
            agent_name=agent_name,
        ).text

    def complete_with_images(
        self,
        *,
        model: str,
        system: str,
        user: str,
        image_jpeg: bytes,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        agent_name: str | None = None,
    ) -> str:
        return cast(SyncLLMClient, self).complete_with_images_ex(
            model=model,
            system=system,
            user=user,
            image_jpeg=image_jpeg,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout_seconds=None,
            agent_name=agent_name,
        ).text

    async def acomplete(
        self,
        *,
        model: str,
        system: str,
        user: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        agent_name: str | None = None,
    ) -> str:
        res = await cast(AsyncLLMClient, self).acomplete_ex(
            model=model,
            system=system,
            user=user,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout_seconds=None,
            agent_name=agent_name,
        )
        return res.text

    async def acomplete_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        agent_name: str | None = None,
    ) -> str:
        res = await cast(AsyncLLMClient, self).acomplete_chat_ex(
            model=model,
            messages=messages,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout_seconds=None,
            agent_name=agent_name,
        )
        return res.text

    async def acomplete_with_images(
        self,
        *,
        model: str,
        system: str,
        user: str,
        image_jpeg: bytes,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        agent_name: str | None = None,
    ) -> str:
        res = await cast(AsyncLLMClient, self).acomplete_with_images_ex(
            model=model,
            system=system,
            user=user,
            image_jpeg=image_jpeg,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout_seconds=None,
            agent_name=agent_name,
        )
        return res.text



_DEFAULT_BUILDER_CODE = """from __future__ import annotations

from manim import Scene


class GeneratedScene(Scene):
    def construct(self) -> None:
        self.wait(0.2)
"""


class FakeLLMClient(LLMClientMixin):
    """Deterministic client for CI and integration tests (no network)."""

    def __init__(
        self,
        *,
        director_text: str | None = None,
        planner_json: str | None = None,
        builder_code: str | None = None,
        sync_segments_json: str | None = None,
        code_review_json: str | None = None,
        visual_review_json: str | None = None,
    ) -> None:
        self._director_text = director_text or (
            "# Storyboard\n\n## Beat 1 — Intro\nExplain the problem in plain language.\n"
        )
        self._planner_json = planner_json or (
            '{"version":"1","beats":[{"step_label":"intro","narration_hint":"Open",'
            '"primitives":[{"name":"title_card","args":{"title":"Demo"}}]}]}'
        )
        self._builder_code = builder_code or _DEFAULT_BUILDER_CODE
        self._sync_json = sync_segments_json or '{"version":"1","beats":[]}'
        self._code_review_json = code_review_json or '{"issues":[]}'
        self._visual_review_json = visual_review_json or '{"issues":[]}'

    def _fake_text(self, *, system: str, user: str, json_mode: bool) -> str:
        _ = user
        s = system.lower()
        if json_mode:
            if "planner agent" in s:
                return self._planner_json
            if "sync engine" in s:
                return self._sync_json
            if "code reviewer" in s:
                return self._code_review_json
            if "visual reviewer" in s:
                return self._visual_review_json
            return self._planner_json
        if "builder agent" in s:
            return self._builder_code
        if "visual reviewer" in s:
            return self._visual_review_json
        if "code reviewer" in s:
            return self._code_review_json
        return self._director_text

    def complete_ex(
        self,
        *,
        model: str,
        system: str,
        user: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
        agent_name: str | None = None,
    ) -> LLMCompletion:
        _ = (model, temperature, max_tokens, request_timeout_seconds, agent_name)
        text = self._fake_text(system=system, user=user, json_mode=json_mode)
        return LLMCompletion(
            text=text,
            usage=LLMUsage(prompt_tokens=0, completion_tokens=0, duration_ms=1),
        )

    def complete_chat_ex(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
        agent_name: str | None = None,
    ) -> LLMCompletion:
        _ = (model, temperature, max_tokens, request_timeout_seconds, agent_name)
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        text = self._fake_text(system=system, user=user, json_mode=json_mode)
        return LLMCompletion(
            text=text,
            usage=LLMUsage(prompt_tokens=0, completion_tokens=0, duration_ms=1),
        )

    def complete_with_images_ex(
        self,
        *,
        model: str,
        system: str,
        user: str,
        image_jpeg: bytes,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
        agent_name: str | None = None,
    ) -> LLMCompletion:
        _ = (model, system, user, image_jpeg, temperature, max_tokens, request_timeout_seconds, agent_name)
        return LLMCompletion(
            text=self._visual_review_json,
            usage=LLMUsage(prompt_tokens=0, completion_tokens=0, duration_ms=1),
        )

    async def acomplete_ex(self, **kwargs: Any) -> LLMCompletion:
        return self.complete_ex(**kwargs)

    async def acomplete_chat_ex(self, **kwargs: Any) -> LLMCompletion:
        return self.complete_chat_ex(**kwargs)

    async def acomplete_with_images_ex(self, **kwargs: Any) -> LLMCompletion:
        return self.complete_with_images_ex(**kwargs)


class LiteLLMClient(LLMClientMixin):
    """LiteLLM-backed client (OpenRouter or any LiteLLM-supported provider)."""

    def __init__(
        self,
        api_key: str | None,
        *,
        api_base: str | None = None,
        provider_keys: dict[str, str] | None = None,
        provider_bases: dict[str, str] | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_base = (api_base or "").strip() or None
        self._provider_keys = provider_keys or {}
        self._provider_bases = provider_bases or {}

        # Load agent_models.yaml config
        from backend.core.config import settings

        from ai_engine.config import default_agent_models_path, load_agent_models_yaml
        
        cfg_path = Path(settings.agent_models_yaml).expanduser() if settings.agent_models_yaml else default_agent_models_path()
        try:
            self._config_data = load_agent_models_yaml(cfg_path)
        except Exception as e:
            logger.warning(f"Could not load agent models yaml from {cfg_path}: {e}")
            self._config_data = {}

        self._rotators: dict[str, KeyRotator] = {}
        providers = self._config_data.get("providers") or {}
        for provider_name, provider_cfg in providers.items():
            if isinstance(provider_cfg, dict):
                keys = provider_cfg.get("keys") or []
                if not isinstance(keys, list):
                    keys = []

                if provider_name == "google_ai_studio":
                    env_keys = []
                    if "GOOGLE_API_KEY" in os.environ:
                        val = os.environ["GOOGLE_API_KEY"]
                        env_keys = [k.strip() for k in val.split(",") if k.strip()]
                    else:
                        idx = 1
                        while True:
                            k_val = os.environ.get(f"GOOGLE_API_KEY_{idx}")
                            if not k_val:
                                break
                            env_keys.append(k_val.strip())
                            idx += 1
                    if env_keys:
                        keys = env_keys

                if keys:
                    self._rotators[provider_name] = KeyRotator([str(k) for k in keys])

    def _get_completion_kwargs(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        timeout: float,
        agent_name: str | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout,
        }

        # Determine provider and credentials based on agent_name
        provider_name = None
        if agent_name and hasattr(self, "_config_data"):
            agents_cfg = self._config_data.get("agents") or {}
            agent_cfg = agents_cfg.get(agent_name)
            if isinstance(agent_cfg, dict):
                provider_name = agent_cfg.get("provider")

        # Get key and base url from rotator/config if provider is found
        api_key = None
        api_base = None

        if provider_name and provider_name in self._rotators:
            api_key = self._rotators[provider_name].get_next_key()
            providers_cfg = self._config_data.get("providers") or {}
            prov_cfg = providers_cfg.get(provider_name) or {}
            if isinstance(prov_cfg, dict):
                api_base = prov_cfg.get("base_url")

        # Fallback to defaults
        if not api_key:
            lowered_model = model.lower()
            if "dashscope/" in lowered_model or "qwen" in lowered_model:
                api_key = self._provider_keys.get("dashscope")
                api_base = self._provider_bases.get("dashscope") or self._api_base
                if not api_base and ("openai/" in lowered_model or "dashscope-intl" not in lowered_model):
                    api_base = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
            else:
                api_key = self._api_key
                api_base = self._provider_bases.get("openrouter") or self._api_base

        if api_key:
            kwargs["api_key"] = api_key
        if api_base:
            kwargs["api_base"] = api_base

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        effective_base = kwargs.get("api_base") or self._api_base or ""
        if "11434" in effective_base:
            kwargs["extra_body"] = {"num_ctx": 16384, "num_predict": -1}

        lowered_model = model.lower()
        if "reasoning" in lowered_model:
            eb = kwargs.get("extra_body") or {}
            eb["reasoning"] = {"enabled": True}
            kwargs["extra_body"] = eb

        return kwargs

    def complete_ex(
        self,
        *,
        model: str,
        system: str,
        user: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
        agent_name: str | None = None,
    ) -> LLMCompletion:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return self.complete_chat_ex(
            model=model,
            messages=messages,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout_seconds=request_timeout_seconds,
            agent_name=agent_name,
        )

    def complete_chat_ex(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
        agent_name: str | None = None,
    ) -> LLMCompletion:
        import litellm
        from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=2, max=10),
            retry=retry_if_exception_type(
                (
                    litellm.APIConnectionError,  # type: ignore
                    litellm.Timeout,  # type: ignore
                    litellm.RateLimitError,  # type: ignore
                    litellm.ServiceUnavailableError,  # type: ignore
                    litellm.InternalServerError,  # type: ignore
                    litellm.APIError,  # type: ignore
                    RuntimeError,
                )
            ),
            reraise=True,
        )
        def _call_with_retry() -> LLMCompletion:
            t0 = time.monotonic()
            timeout = float(request_timeout_seconds or 600)
            kwargs = self._get_completion_kwargs(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
                timeout=timeout,
                agent_name=agent_name,
            )

            resp = litellm.completion(**kwargs)
            msg = resp.choices[0].message
            content = getattr(msg, "content", None)

            if not content:
                fields = list(msg.model_dump().keys()) if hasattr(msg, "model_dump") else []
                logger.debug(f"DEBUG: LLM message fields: {fields}")
                for field in ["reasoning", "reasoning_content", "thought"]:
                    val = getattr(msg, field, None)
                    if val and isinstance(val, str) and val.strip():
                        content = val
                        break

            text = content.strip() if isinstance(content, str) else ""
            if not text:
                logger.error(
                    "LiteLLM returned empty content (model=%s). Message fields: %s",
                    model,
                    list(msg.keys()) if hasattr(msg, "keys") else [],
                )
                raise RuntimeError("LLM returned empty content")
            duration_ms = int((time.monotonic() - t0) * 1000)
            usage_obj = getattr(resp, "usage", None)
            pt = getattr(usage_obj, "prompt_tokens", None) if usage_obj is not None else None
            ct = getattr(usage_obj, "completion_tokens", None) if usage_obj is not None else None
            usage = LLMUsage(
                prompt_tokens=pt,
                completion_tokens=ct,
                duration_ms=duration_ms,
            )
            return LLMCompletion(text=text, usage=usage)

        return _call_with_retry()

    def complete_with_images_ex(
        self,
        *,
        model: str,
        system: str,
        user: str,
        image_jpeg: bytes,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
        agent_name: str | None = None,
    ) -> LLMCompletion:
        import litellm
        from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

        @retry(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=2, min=4, max=20),
            retry=retry_if_exception_type(
                (
                    litellm.APIConnectionError,  # type: ignore
                    litellm.Timeout,  # type: ignore
                    litellm.RateLimitError,  # type: ignore
                    litellm.ServiceUnavailableError,  # type: ignore
                    litellm.InternalServerError,  # type: ignore
                    litellm.APIError,  # type: ignore
                )
            ),
            reraise=True,
        )
        def _call_with_retry() -> LLMCompletion:
            t0 = time.monotonic()
            b64 = base64.standard_b64encode(image_jpeg).decode("ascii")
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                },
            ]
            timeout = float(request_timeout_seconds or 600)
            kwargs = self._get_completion_kwargs(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
                timeout=timeout,
                agent_name=agent_name,
            )

            resp = litellm.completion(**kwargs)
            msg = resp.choices[0].message
            content = getattr(msg, "content", None)
            text = content.strip() if isinstance(content, str) else ""
            if not text:
                logger.error("LiteLLM vision returned empty content (model=%s)", model)
                raise RuntimeError("LLM returned empty content")
            duration_ms = int((time.monotonic() - t0) * 1000)
            usage_obj = getattr(resp, "usage", None)
            pt = getattr(usage_obj, "prompt_tokens", None) if usage_obj is not None else None
            ct = getattr(usage_obj, "completion_tokens", None) if usage_obj is not None else None
            usage = LLMUsage(
                prompt_tokens=pt,
                completion_tokens=ct,
                duration_ms=duration_ms,
            )
            return LLMCompletion(text=text, usage=usage)

        return _call_with_retry()

    async def acomplete_ex(
        self,
        *,
        model: str,
        system: str,
        user: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
        agent_name: str | None = None,
    ) -> LLMCompletion:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return await self.acomplete_chat_ex(
            model=model,
            messages=messages,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout_seconds=request_timeout_seconds,
            agent_name=agent_name,
        )

    async def acomplete_chat_ex(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
        agent_name: str | None = None,
    ) -> LLMCompletion:
        import litellm
        from tenacity import (
            AsyncRetrying,
            retry_if_exception_type,
            stop_after_attempt,
            wait_exponential,
        )

        t0 = time.monotonic()
        timeout = float(request_timeout_seconds or 600)
        kwargs = self._get_completion_kwargs(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            timeout=timeout,
            agent_name=agent_name,
        )

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=2, max=10),
            retry=retry_if_exception_type(
                (
                    litellm.APIConnectionError,  # type: ignore
                    litellm.Timeout,  # type: ignore
                    litellm.RateLimitError,  # type: ignore
                    litellm.ServiceUnavailableError,  # type: ignore
                    litellm.InternalServerError,  # type: ignore
                    litellm.APIError,  # type: ignore
                    RuntimeError,
                )
            ),
            reraise=True,
        ):
            with attempt:
                resp = await litellm.acompletion(**kwargs)

        msg = resp.choices[0].message
        content = getattr(msg, "content", None)
        if not content:
            for field in ["reasoning", "reasoning_content", "thought"]:
                val = getattr(msg, field, None)
                if val and isinstance(val, str) and val.strip():
                    content = val
                    break

        text = content.strip() if isinstance(content, str) else ""
        if not text:
            raise RuntimeError("LLM returned empty content")

        duration_ms = int((time.monotonic() - t0) * 1000)
        usage_obj = getattr(resp, "usage", None)
        usage = LLMUsage(
            prompt_tokens=getattr(usage_obj, "prompt_tokens", None),
            completion_tokens=getattr(usage_obj, "completion_tokens", None),
            duration_ms=duration_ms,
        )
        return LLMCompletion(text=text, usage=usage)

    async def acomplete_with_images_ex(
        self,
        *,
        model: str,
        system: str,
        user: str,
        image_jpeg: bytes,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
        agent_name: str | None = None,
    ) -> LLMCompletion:
        import litellm
        from tenacity import (
            AsyncRetrying,
            retry_if_exception_type,
            stop_after_attempt,
            wait_exponential,
        )

        t0 = time.monotonic()
        b64 = base64.standard_b64encode(image_jpeg).decode("ascii")
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            },
        ]
        timeout = float(request_timeout_seconds or 600)
        kwargs = self._get_completion_kwargs(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            timeout=timeout,
            agent_name=agent_name,
        )

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=2, min=4, max=20),
            retry=retry_if_exception_type(
                (
                    litellm.APIConnectionError,  # type: ignore
                    litellm.Timeout,  # type: ignore
                    litellm.RateLimitError,  # type: ignore
                    litellm.ServiceUnavailableError,  # type: ignore
                    litellm.InternalServerError,  # type: ignore
                    litellm.APIError,  # type: ignore
                )
            ),
            reraise=True,
        ):
            with attempt:
                resp = await litellm.acompletion(**kwargs)

        msg = resp.choices[0].message
        content = getattr(msg, "content", None)
        text = content.strip() if isinstance(content, str) else ""
        if not text:
            raise RuntimeError("LLM returned empty content")

        duration_ms = int((time.monotonic() - t0) * 1000)
        usage_obj = getattr(resp, "usage", None)
        usage = LLMUsage(
            prompt_tokens=getattr(usage_obj, "prompt_tokens", None),
            completion_tokens=getattr(usage_obj, "completion_tokens", None),
            duration_ms=duration_ms,
        )
        return LLMCompletion(text=text, usage=usage)
