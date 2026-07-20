from __future__ import annotations

import logging
import os
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

import redis
import litellm
from litellm import acompletion, completion

litellm.drop_params = True

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


redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


class _KeyStateStore(Protocol):
    def exists(self, key: str) -> int | bool: ...

    def hset(self, key: str, *, mapping: dict[str, object]) -> object: ...

    def hgetall(self, key: str) -> dict[str, str]: ...

    def incr(self, key: str) -> int: ...


class _MemoryKeyStateStore:
    """Tiny isolated store for ad-hoc pools and unit tests without Redis."""

    def __init__(self) -> None:
        self._hashes: dict[str, dict[str, str]] = {}
        self._counters: dict[str, int] = {}
        self._lock = threading.Lock()

    def exists(self, key: str) -> bool:
        with self._lock:
            return key in self._hashes

    def hset(self, key: str, *, mapping: dict[str, object]) -> int:
        with self._lock:
            current = self._hashes.setdefault(key, {})
            current.update({name: str(value) for name, value in mapping.items()})
        return len(mapping)

    def hgetall(self, key: str) -> dict[str, str]:
        with self._lock:
            return dict(self._hashes.get(key, {}))

    def incr(self, key: str) -> int:
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + 1
            return self._counters[key]


class GoogleAPIKeyPool:
    """Stateful Google key selection using Redis to share state across workers."""

    def __init__(
        self,
        keys: list[str],
        *,
        namespace: str | None = None,
        redis_store: _KeyStateStore | None = None,
    ) -> None:
        self._keys = [key for key in dict.fromkeys(keys) if key]
        # Ad-hoc pools are isolated, which makes tests and one-off probes
        # deterministic. The process-wide production pool below supplies a
        # stable namespace so cooldown state remains shared across workers.
        self._prefix = f"{namespace or f'ai_keys:pool:{uuid4()}'}:"
        self._redis: _KeyStateStore = (
            redis_store or (redis_client if namespace else _MemoryKeyStateStore())
        )

    def _state(self, key: str) -> dict[str, str]:
        state_key = f"{self._prefix}{key}"
        if not self._redis.exists(state_key):
            self._redis.hset(
                state_key,
                mapping={"state": KeyState.AVAILABLE, "retry_at": "0"},
            )
        return self._redis.hgetall(state_key)

    def acquire(self) -> tuple[str, str]:
        now = datetime.now(tz=UTC).timestamp()
        for _ in range(len(self._keys)):
            idx = (self._redis.incr(f"{self._prefix}index") - 1) % len(self._keys)
            key = self._keys[idx]

            state_data = self._state(key)
            state = state_data.get("state", KeyState.AVAILABLE)
            retry_at = float(state_data.get("retry_at", "0"))

            if state == KeyState.AVAILABLE or (retry_at > 0 and now >= retry_at):
                if state != KeyState.AVAILABLE:
                    self._redis.hset(
                        f"{self._prefix}{key}",
                        mapping={"state": KeyState.AVAILABLE, "retry_at": "0"},
                    )
                return key, key
        raise RuntimeError("No AVAILABLE Google API key")

    def record_failure(self, identity: str, error: BaseException) -> None:
        message = str(error).lower()
        quota = "quota" in message or "resource_exhausted" in message
        rate_limited = "429" in message or "rate limit" in message or "too many requests" in message
        if not quota and not rate_limited:
            return

        self._state(identity)
        now = datetime.now(tz=UTC)
        if "requestsperday" in message or "requests per day" in message:
            tomorrow = (now + timedelta(days=1)).date()
            retry_at = datetime.combine(tomorrow, datetime.min.time(), tzinfo=UTC).timestamp()
            self._redis.hset(
                f"{self._prefix}{identity}",
                mapping={"state": KeyState.EXHAUSTED, "retry_at": str(retry_at)},
            )
        else:
            retry_at = (now + timedelta(seconds=60)).timestamp()
            self._redis.hset(
                f"{self._prefix}{identity}",
                mapping={"state": KeyState.COOLDOWN, "retry_at": str(retry_at)},
            )

    def snapshot(self) -> list[dict[str, str | None]]:
        res = []
        for key in self._keys:
            state_data = self._state(key)
            state = state_data.get("state", KeyState.AVAILABLE)
            retry_at = float(state_data.get("retry_at", "0"))
            retry_str = datetime.fromtimestamp(retry_at, tz=UTC).isoformat() if retry_at > 0 else None
            res.append({"state": state, "retry_at": retry_str})
        return res


def configured_google_keys() -> list[str]:
    values: list[str] = []
    configured = settings.google_api_key or os.getenv("GEMINI_API_KEY")
    if configured:
        values.extend(value.strip() for value in configured.split(",") if value.strip())
    index = 1
    while key := os.getenv(f"GOOGLE_API_KEY_{index}"):
        values.append(key.strip())
        index += 1
    return list(dict.fromkeys(values))


_SHARED_POOL = GoogleAPIKeyPool(configured_google_keys(), namespace="ai_keys:shared")


class GoogleLLM:
    def __init__(self, pool: GoogleAPIKeyPool | None = None) -> None:
        self.pool = pool or _SHARED_POOL

    @staticmethod
    def _model_name(model: str) -> str:
        return model if "/" in model else f"openai/{model}"

    @staticmethod
    def _reasoning_kwargs(model: str, reasoning_effort: str) -> dict[str, str]:
        # Gemma chat models exposed by this endpoint do not advertise the
        # reasoning_effort parameter. Omitting it is different from asking the
        # provider for an unsupported mode.
        if reasoning_effort == "none" or "gemma" in model.lower():
            return {}
        return {"reasoning_effort": reasoning_effort}

    def complete(
        self, *, messages: list[dict[str, str]], model: str, temperature: float,
        max_tokens: int, reasoning_effort: str = "none"
    ) -> str:
        logger = logging.getLogger(__name__)
        last_exc: BaseException | None = None

        for _ in range(len(self.pool._keys)):
            try:
                key, identity = self.pool.acquire()
            except RuntimeError as exc:
                if last_exc:
                    raise last_exc from exc
                raise
            try:
                response = completion(
                    model=self._model_name(model),
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    api_key=key,
                    api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
                    timeout=600,
                    **self._reasoning_kwargs(model, reasoning_effort),
                )
                return str(response.choices[0].message.content or "")
            except Exception as exc:  # noqa: BLE001
                self.pool.record_failure(identity, exc)
                last_exc = exc
                logger.warning("Key failed in complete, trying next: %s", exc)

        if last_exc:
            raise last_exc
        raise RuntimeError("No AVAILABLE Google API key")

    def complete_with_image(
        self,
        *,
        messages: list[dict],
        image_bytes: bytes,
        image_media_type: str = "image/png",
        model: str,
        temperature: float,
        max_tokens: int,
        reasoning_effort: str = "none",
    ) -> str:
        """Vision-language completion with an inline base64 image."""
        import base64

        b64 = base64.b64encode(image_bytes).decode()
        data_url = f"data:{image_media_type};base64,{b64}"
        vision_messages: list[dict] = []
        for msg in messages:
            if msg.get("role") == "user":
                text = msg.get("content", "")
                vision_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": text if isinstance(text, str) else str(text)},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                )
            else:
                vision_messages.append(msg)
        return self.complete(
            messages=vision_messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        )

    async def stream(
        self, *, messages: list[dict[str, str]], model: str, temperature: float,
        max_tokens: int, reasoning_effort: str = "none"
    ) -> AsyncIterator[str]:
        logger = logging.getLogger(__name__)
        last_exc: BaseException | None = None

        for _ in range(len(self.pool._keys)):
            try:
                key, identity = self.pool.acquire()
            except RuntimeError as exc:
                if last_exc:
                    raise last_exc from exc
                raise
            try:
                response = await acompletion(
                    model=self._model_name(model),
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    api_key=key,
                    api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
                    timeout=600,
                    stream=True,
                    **self._reasoning_kwargs(model, reasoning_effort),
                )

                # Dry run the first token to verify the key works
                iterator = response.__aiter__()
                try:
                    first_chunk = await iterator.__anext__()
                except StopAsyncIteration:
                    return

                delta = first_chunk.choices[0].delta.content if first_chunk.choices else None
                if delta:
                    yield str(delta)

                async for chunk in iterator:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        yield str(delta)
                return
            except Exception as exc:  # noqa: BLE001
                self.pool.record_failure(identity, exc)
                last_exc = exc
                logger.warning("Key failed in stream, trying next: %s", exc)

        if last_exc:
            raise last_exc
        raise RuntimeError("No AVAILABLE Google API key")
