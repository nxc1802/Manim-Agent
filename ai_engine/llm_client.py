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
        if json_mode:
            s = system.lower()
            if "planner agent" in s:
                return self._planner_json
            if "sync engine" in s:
                return self._sync_json
            if "code reviewer" in s:
                return self._code_review_json
            return self._planner_json
        if "Builder agent" in system:
            return self._builder_code
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


class LiteLLMClient:
    """LiteLLM-backed client (OpenRouter or any LiteLLM-supported provider)."""

    def __init__(self, api_key: str | None, *, api_base: str | None = None) -> None:
        self._api_key = api_key
        self._api_base = (api_base or "").strip() or None

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
        import litellm

        t0 = time.monotonic()
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

        t0 = time.monotonic()
        timeout = float(request_timeout_seconds or 600)
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout,
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._api_base:
            kwargs["api_base"] = self._api_base
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp = litellm.completion(**kwargs)
        msg = resp.choices[0].message
        content = getattr(msg, "content", None)
        text = content.strip() if isinstance(content, str) else ""
        if not text:
            logger.error("LiteLLM returned empty content (model=%s)", model)
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
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout,
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._api_base:
            kwargs["api_base"] = self._api_base
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

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
