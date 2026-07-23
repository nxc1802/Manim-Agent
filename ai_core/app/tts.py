from __future__ import annotations

import base64
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.llm import _SHARED_POOL, GoogleAPIKeyPool, _redacted_provider_error, configured_google_keys

logger = logging.getLogger(__name__)

_GEMINI_TTS_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-tts-preview:generateContent"
)
_CLOUD_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
_MAX_SYNTHESIS_CHARS = 4_500


class TtsSynthesisError(RuntimeError):
    """A user-actionable failure from the configured speech provider."""


def synthesize_speech(
    *,
    narration: str | None,
    source_language: str | None,
    user_settings: dict[str, Any],
    destination: Path,
) -> Path | None:
    """Create an MP3 narration only when TTS is explicitly enabled.

    Uses Gemini 3.1 Flash TTS by default, with fallback to Cloud TTS.
    Shares the Redis key pool, rotation, and cooldown logic with LLM completions.
    """
    if not user_settings.get("tts_enabled", False):
        return None
    text = " ".join((narration or "").split())
    if not text:
        raise TtsSynthesisError("TTS is enabled but this scene has no narration to synthesize")
    if len(text) > _MAX_SYNTHESIS_CHARS:
        raise TtsSynthesisError(
            f"Scene narration is too long for synchronous TTS ({len(text)} characters)"
        )

    keys = configured_google_keys()
    if not keys:
        raise TtsSynthesisError("TTS is enabled but GOOGLE_API_KEY is not configured")

    pool = _SHARED_POOL if _SHARED_POOL._keys == keys else GoogleAPIKeyPool(keys)

    last_exc: BaseException | None = None
    for _ in range(len(keys)):
        try:
            key, identity = pool.acquire()
        except RuntimeError:
            if last_exc:
                raise TtsSynthesisError(
                    f"Text-to-Speech synthesis failed: {_redacted_provider_error(last_exc, keys)}"
                ) from None
            raise TtsSynthesisError("TTS is enabled but no Google API key is AVAILABLE") from None

        # Try Gemini 3.1 Flash TTS first (Free AI Studio Developer API model)
        pcm_path: Path | None = None
        try:
            gemini_payload = {
                "contents": [{"parts": [{"text": text}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": "Puck"
                            }
                        }
                    }
                }
            }
            resp = httpx.post(
                _GEMINI_TTS_URL,
                headers={"x-goog-api-key": key},
                json=gemini_payload,
                timeout=settings.tts_timeout_seconds,
            )
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and "inlineData" in parts[0]:
                        raw_b64 = parts[0]["inlineData"].get("data")
                        if raw_b64:
                            pcm_bytes = base64.b64decode(raw_b64)
                            with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as pcm_file:
                                pcm_file.write(pcm_bytes)
                                pcm_path = Path(pcm_file.name)

                            cmd = [
                                "ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1",
                                "-i", str(pcm_path), str(destination)
                            ]
                            res = subprocess.run(
                                cmd,
                                capture_output=True,
                                timeout=settings.tts_timeout_seconds,
                                check=False,
                            )
                            if res.returncode == 0 and destination.is_file() and destination.stat().st_size > 0:
                                return destination
            elif resp.status_code in {429, 403, 500, 503}:
                resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            pool.record_failure(identity, exc)
            last_exc = exc
            logger.warning("Gemini Flash TTS failed on key, trying fallback/next key: %s", _redacted_provider_error(exc, keys))
        finally:
            if pcm_path is not None:
                pcm_path.unlink(missing_ok=True)

        # Fallback to Google Cloud Text-to-Speech API
        requested_voice = str(user_settings.get("tts_voice") or "auto")
        voice_mapping = {
            "vi-VN-female": "vi-VN-Standard-A",
            "vi-VN-male": "vi-VN-Standard-B",
            "en-US-female": "en-US-Standard-C",
            "en-US-male": "en-US-Standard-D",
        }
        mapped_voice = voice_mapping.get(requested_voice, requested_voice)
        if mapped_voice == "auto":
            voice_name = (
                "vi-VN-Standard-A"
                if str(source_language or "en").lower().startswith("vi")
                else "en-US-Standard-C"
            )
        else:
            voice_name = mapped_voice
        language_code = "vi-VN" if voice_name.startswith("vi-") else "en-US"

        payload = {
            "input": {"text": text},
            "voice": {"languageCode": language_code, "name": voice_name},
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": float(user_settings.get("tts_speaking_rate", 1)),
                "pitch": float(user_settings.get("tts_pitch", 0)),
            },
        }
        try:
            response = httpx.post(
                _CLOUD_TTS_URL,
                headers={"x-goog-api-key": key},
                json=payload,
                timeout=settings.tts_timeout_seconds,
            )
            response.raise_for_status()
            encoded_audio = response.json().get("audioContent")
            if not isinstance(encoded_audio, str) or not encoded_audio:
                raise TtsSynthesisError("TTS returned no audio content")
            audio_bytes = base64.b64decode(encoded_audio, validate=True)
            if audio_bytes:
                destination.write_bytes(audio_bytes)
                return destination
        except Exception as exc:  # noqa: BLE001
            pool.record_failure(identity, exc)
            last_exc = exc
            logger.warning("Cloud TTS failed on key, trying next key: %s", _redacted_provider_error(exc, keys))

    if last_exc:
        raise TtsSynthesisError(
            f"Text-to-Speech synthesis failed; verify your GOOGLE_API_KEY: {_redacted_provider_error(last_exc, keys)}"
        ) from last_exc
    raise TtsSynthesisError("TTS is enabled but no Google API key is AVAILABLE")
