from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMUsage:
    prompt_tokens: int | None
    completion_tokens: int | None
    duration_ms: int


@dataclass(frozen=True)
class LLMCompletion:
    text: str
    usage: LLMUsage


@runtime_checkable
class LLMClient(Protocol):
    """Text + optional single-image completion (all LLM agents run in the API process)."""

    def complete(
        self,
        *,
        model: str,
        system: str,
        user: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
    ) -> str: ...

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
    ) -> LLMCompletion: ...

    def complete_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
    ) -> str: ...

    def complete_chat_ex(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
    ) -> LLMCompletion: ...

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
    ) -> str: ...

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
    ) -> LLMCompletion: ...

    async def acomplete(
        self,
        *,
        model: str,
        system: str,
        user: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
    ) -> str: ...

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
    ) -> LLMCompletion: ...

    async def acomplete_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
    ) -> str: ...

    async def acomplete_chat_ex(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
    ) -> LLMCompletion: ...

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
    ) -> str: ...

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
    ) -> LLMCompletion: ...


_DEFAULT_BUILDER_CODE = """from __future__ import annotations

from manim import Scene


class GeneratedScene(Scene):
    def construct(self) -> None:
        self.wait(0.2)
"""


class FakeLLMClient:
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

    def complete(
        self,
        *,
        model: str,
        system: str,
        user: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
    ) -> str:
        _ = (model, temperature, max_tokens)
        return self._fake_text(system=system, user=user, json_mode=json_mode)

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
    ) -> LLMCompletion:
        _ = (model, temperature, max_tokens, request_timeout_seconds)
        text = self._fake_text(system=system, user=user, json_mode=json_mode)
        return LLMCompletion(
            text=text,
            usage=LLMUsage(prompt_tokens=0, completion_tokens=0, duration_ms=1),
        )

    def complete_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
    ) -> str:
        return self.complete_chat_ex(
            model=model,
            messages=messages,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout_seconds=None,
        ).text

    def complete_chat_ex(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
    ) -> LLMCompletion:
        _ = (model, temperature, max_tokens, request_timeout_seconds)
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        text = self._fake_text(system=system, user=user, json_mode=json_mode)
        return LLMCompletion(
            text=text,
            usage=LLMUsage(prompt_tokens=0, completion_tokens=0, duration_ms=1),
        )

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
    ) -> str:
        return self.complete_with_images_ex(
            model=model,
            system=system,
            user=user,
            image_jpeg=image_jpeg,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout_seconds=None,
        ).text

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
    ) -> LLMCompletion:
        _ = (model, system, user, image_jpeg, temperature, max_tokens, request_timeout_seconds)
        return LLMCompletion(
            text=self._visual_review_json,
            usage=LLMUsage(prompt_tokens=0, completion_tokens=0, duration_ms=1),
        )

    async def acomplete(self, **kwargs: Any) -> str:
        return self.complete(**kwargs)

    async def acomplete_ex(self, **kwargs: Any) -> LLMCompletion:
        return self.complete_ex(**kwargs)

    async def acomplete_chat(self, **kwargs: Any) -> str:
        return self.complete_chat(**kwargs)

    async def acomplete_chat_ex(self, **kwargs: Any) -> LLMCompletion:
        return self.complete_chat_ex(**kwargs)

    async def acomplete_with_images(self, **kwargs: Any) -> str:
        return self.complete_with_images(**kwargs)

    async def acomplete_with_images_ex(self, **kwargs: Any) -> LLMCompletion:
        return self.complete_with_images_ex(**kwargs)


class LiteLLMClient:
    """LiteLLM-backed client (OpenRouter or any LiteLLM-supported provider)."""

    def __init__(
        self,
        api_key: str | None,
        *,
        api_base: str | None = None,
        provider_keys: dict[str, str] | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_base = (api_base or "").strip() or None
        self._provider_keys = provider_keys or {}

    def complete(
        self,
        *,
        model: str,
        system: str,
        user: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
    ) -> str:
        return self.complete_ex(
            model=model,
            system=system,
            user=user,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout_seconds=None,
        ).text

    def _get_completion_kwargs(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        timeout: float,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout,
        }

        # Multi-provider logic
        lowered_model = model.lower()
        if "dashscope/" in lowered_model or "qwen" in lowered_model:
            ds_key = self._provider_keys.get("dashscope")
            if ds_key:
                kwargs["api_key"] = ds_key
                # Use the compatible-mode base if it's an 'openai/' style call
                # or we want to force it
                if "openai/" in lowered_model or "dashscope-intl" not in lowered_model:
                    kwargs["api_base"] = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        elif "openrouter/" in lowered_model or "/" not in model:
            if self._api_key:
                kwargs["api_key"] = self._api_key
            if self._api_base:
                kwargs["api_base"] = self._api_base

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        # Ollama specific overrides
        effective_base = kwargs.get("api_base") or self._api_base or ""
        if "11434" in effective_base:
            kwargs["extra_body"] = {"num_ctx": 16384, "num_predict": -1}

        # reasoning specific overrides
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
    ) -> LLMCompletion:

        time.monotonic()
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
        )

    def complete_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
    ) -> str:
        return self.complete_chat_ex(
            model=model,
            messages=messages,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout_seconds=None,
        ).text

    def complete_chat_ex(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
    ) -> LLMCompletion:
        import litellm
        from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=2, max=10),
            retry=retry_if_exception_type(
                (
                    litellm.APIConnectionError,
                    litellm.Timeout,
                    litellm.RateLimitError,
                    litellm.ServiceUnavailableError,
                    litellm.InternalServerError,
                    litellm.APIError,
                    RuntimeError,  # covers "LLM returned empty content"
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
            )

            resp = litellm.completion(**kwargs)
            msg = resp.choices[0].message
            content = getattr(msg, "content", None)

            # Debug: Check for reasoning content or other fields if standard content is empty
            if not content:
                # msg.model_dump() provides a dict view in Pydantic v2
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
                    list(msg.keys()),
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
    ) -> str:
        return self.complete_with_images_ex(
            model=model,
            system=system,
            user=user,
            image_jpeg=image_jpeg,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout_seconds=None,
        ).text

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
    ) -> LLMCompletion:
        import litellm
        from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

        @retry(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=2, min=4, max=20),
            retry=retry_if_exception_type(
                (
                    litellm.APIConnectionError,
                    litellm.Timeout,
                    litellm.RateLimitError,
                    litellm.ServiceUnavailableError,
                    litellm.InternalServerError,
                    litellm.APIError,
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

    async def acomplete(
        self,
        *,
        model: str,
        system: str,
        user: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
    ) -> str:
        res = await self.acomplete_ex(
            model=model,
            system=system,
            user=user,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout_seconds=None,
        )
        return res.text

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
        )

    async def acomplete_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
    ) -> str:
        res = await self.acomplete_chat_ex(
            model=model,
            messages=messages,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout_seconds=None,
        )
        return res.text

    async def acomplete_chat_ex(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: int | None,
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
        )

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=2, max=10),
            retry=retry_if_exception_type(
                (
                    litellm.APIConnectionError,
                    litellm.Timeout,
                    litellm.RateLimitError,
                    litellm.ServiceUnavailableError,
                    litellm.InternalServerError,
                    litellm.APIError,
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
    ) -> str:
        res = await self.acomplete_with_images_ex(
            model=model,
            system=system,
            user=user,
            image_jpeg=image_jpeg,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout_seconds=None,
        )
        return res.text

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
        messages = [
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
        )

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=2, min=4, max=20),
            retry=retry_if_exception_type(
                (
                    litellm.APIConnectionError,
                    litellm.Timeout,
                    litellm.RateLimitError,
                    litellm.ServiceUnavailableError,
                    litellm.InternalServerError,
                    litellm.APIError,
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
