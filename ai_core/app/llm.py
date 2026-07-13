from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from litellm import acompletion, completion

from app.config import settings


class KeyState(StrEnum):
    AVAILABLE = "AVAILABLE"
    COOLDOWN = "COOLDOWN"
    EXHAUSTED = "EXHAUSTED"


@dataclass
class GoogleAPIKey:
    value: str
    state: KeyState = KeyState.AVAILABLE
    retry_at: datetime | None = None


class GoogleAPIKeyPool:
    """Stateful Google key selection preserved from the former AI pipeline."""

    def __init__(self, keys: list[str]) -> None:
        self._keys = [GoogleAPIKey(value=key) for key in dict.fromkeys(keys) if key]
        self._index = 0
        self._lock = threading.Lock()

    def acquire(self) -> tuple[str, str]:
        with self._lock:
            now = datetime.now(tz=UTC)
            for item in self._keys:
                if item.state is not KeyState.AVAILABLE and item.retry_at and item.retry_at <= now:
                    item.state, item.retry_at = KeyState.AVAILABLE, None
            for offset in range(len(self._keys)):
                index = (self._index + offset) % len(self._keys)
                item = self._keys[index]
                if item.state is KeyState.AVAILABLE:
                    self._index = (index + 1) % len(self._keys)
                    return item.value, item.value
        raise RuntimeError("No AVAILABLE Google API key")

    def record_failure(self, identity: str, error: BaseException) -> None:
        message = str(error).lower()
        quota = "quota" in message or "resource_exhausted" in message
        rate_limited = "429" in message or "rate limit" in message or "too many requests" in message
        if not quota and not rate_limited:
            return
        with self._lock:
            item = next((key for key in self._keys if key.value == identity), None)
            if item is None:
                return
            now = datetime.now(tz=UTC)
            if "requestsperday" in message or "requests per day" in message:
                tomorrow = (now + timedelta(days=1)).date()
                item.state = KeyState.EXHAUSTED
                item.retry_at = datetime.combine(tomorrow, datetime.min.time(), tzinfo=UTC)
            else:
                item.state = KeyState.COOLDOWN
                item.retry_at = now + timedelta(seconds=60)

    def snapshot(self) -> list[dict[str, str | None]]:
        with self._lock:
            return [{"state": key.state, "retry_at": key.retry_at.isoformat() if key.retry_at else None} for key in self._keys]


def _google_keys() -> list[str]:
    values: list[str] = []
    configured = settings.google_api_key or os.getenv("GEMINI_API_KEY")
    if configured:
        values.extend(value.strip() for value in configured.split(",") if value.strip())
    index = 1
    while key := os.getenv(f"GOOGLE_API_KEY_{index}"):
        values.append(key.strip())
        index += 1
    return list(dict.fromkeys(values))


class GoogleLLM:
    def __init__(self, pool: GoogleAPIKeyPool | None = None) -> None:
        self.pool = pool or GoogleAPIKeyPool(_google_keys())

    @staticmethod
    def _model_name(model: str) -> str:
        return model if "/" in model else f"openai/{model}"

    def complete(self, *, messages: list[dict[str, str]], model: str, temperature: float, max_tokens: int) -> str:
        key, identity = self.pool.acquire()
        try:
            response = completion(
                model=self._model_name(model),
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=key,
                api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
                timeout=600,
            )
            return str(response.choices[0].message.content or "")
        except Exception as exc:  # noqa: BLE001
            self.pool.record_failure(identity, exc)
            raise

    def complete_with_image(
        self,
        *,
        messages: list[dict],
        image_bytes: bytes,
        image_media_type: str = "image/png",
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Vision-language completion with an inline base64 image."""
        import base64

        b64 = base64.b64encode(image_bytes).decode()
        data_url = f"data:{image_media_type};base64,{b64}"
        vision_messages: list[dict] = []
        for msg in messages:
            if msg.get("role") == "user":
                text = msg.get("content", "")
                vision_messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text if isinstance(text, str) else str(text)},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                })
            else:
                vision_messages.append(msg)
        return self.complete(
            messages=vision_messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def stream(self, *, messages: list[dict[str, str]], model: str, temperature: float, max_tokens: int) -> AsyncIterator[str]:
        key, identity = self.pool.acquire()
        try:
            response = await acompletion(
                model=self._model_name(model), messages=messages, temperature=temperature,
                max_tokens=max_tokens, api_key=key,
                api_base="https://generativelanguage.googleapis.com/v1beta/openai/", timeout=600, stream=True,
            )
            async for chunk in response:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield str(delta)
        except Exception as exc:  # noqa: BLE001
            self.pool.record_failure(identity, exc)
            raise
        await asyncio.sleep(0)
