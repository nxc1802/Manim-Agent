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

_GEMINI_VOICE_MAPPING = {
    "vi-VN-female": "Puck",
    "vi-VN-male": "Charon",
    "en-US-female": "Puck",
    "en-US-male": "Charon",
    "vi-VN-Standard-A": "Puck",
    "vi-VN-Standard-B": "Charon",
    "en-US-Standard-C": "Puck",
    "en-US-Standard-D": "Charon",
}


class TtsSynthesisError(RuntimeError):
    """A user-actionable failure from the configured speech provider."""


def _split_narration(text: str, limit: int = _MAX_SYNTHESIS_CHARS) -> list[str]:
    """Split long narration near sentence boundaries for synchronous providers."""
    if len(text) <= limit:
        return [text]

    segments: list[str] = []
    remaining = text
    while len(remaining) > limit:
        candidate = remaining[:limit]
        boundary = max(candidate.rfind(mark) for mark in (". ", "! ", "? ", "; ", ", ", " "))
        if boundary < limit // 2:
            boundary = candidate.rfind(" ")
        if boundary <= 0:
            boundary = limit
        segments.append(remaining[:boundary + 1].strip())
        remaining = remaining[boundary + 1 :].strip()
    if remaining:
        segments.append(remaining)
    return segments


def _concat_mp3_segments(segment_paths: list[Path], destination: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="tts_concat_") as temp_dir:
        list_file = Path(temp_dir) / "segments.txt"
        # Segment files are generated in a private temporary directory and do
        # not contain user-controlled paths.
        list_file.write_text(
            "\n".join(f"file '{path}'" for path in segment_paths), encoding="utf-8"
        )
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
                "-c", "copy", str(destination),
            ],
            capture_output=True,
            timeout=settings.tts_timeout_seconds,
            check=False,
        )
        if result.returncode != 0 or not destination.is_file() or destination.stat().st_size == 0:
            raise TtsSynthesisError("Unable to concatenate TTS narration segments")


def _gemini_voice_and_prompt(
    text: str, source_language: str | None, user_settings: dict[str, Any]
) -> tuple[str, str]:
    """Translate the public TTS controls to Gemini's voice/directing model.

    Gemini TTS uses named voices and natural-language direction instead of the
    numeric Cloud TTS rate/pitch fields.  The wording is deliberately separate
    from the transcript so narration remains the content to be spoken.
    """
    requested_voice = str(user_settings.get("tts_voice") or "auto")
    if requested_voice == "auto":
        voice = "Puck" if str(source_language or "en").lower().startswith("vi") else "Kore"
    else:
        voice = _GEMINI_VOICE_MAPPING.get(requested_voice, "Puck")

    rate = float(user_settings.get("tts_speaking_rate", 1))
    pitch = float(user_settings.get("tts_pitch", 0))
    pace = "slow" if rate < 0.9 else "fast" if rate > 1.1 else "natural"
    pitch_direction = "lower-pitched" if pitch < -1 else "higher-pitched" if pitch > 1 else "natural-pitched"
    prompt = (
        f"Read this narration exactly once, with a {pace} pace and a {pitch_direction} voice. "
        f"Do not read these instructions aloud.\n\nNarration:\n{text}"
    )
    return voice, prompt


def synthesize_speech(
    *,
    narration: str | None,
    source_language: str | None,
    user_settings: dict[str, Any],
    destination: Path,
    _split_long_text: bool = True,
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
        if not _split_long_text:
            raise TtsSynthesisError("TTS segment exceeds the synchronous provider limit")
        segments = _split_narration(text)
        with tempfile.TemporaryDirectory(prefix="tts_segments_") as temp_dir:
            temp = Path(temp_dir)
            segment_paths: list[Path] = []
            for index, segment in enumerate(segments):
                segment_path = temp / f"segment_{index:04d}.mp3"
                audio = synthesize_speech(
                    narration=segment,
                    source_language=source_language,
                    user_settings=user_settings,
                    destination=segment_path,
                    _split_long_text=False,
                )
                if audio is None:
                    raise TtsSynthesisError("TTS did not create a narration segment")
                segment_paths.append(audio)
            _concat_mp3_segments(segment_paths, destination)
        return destination

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
            gemini_voice, gemini_text = _gemini_voice_and_prompt(text, source_language, user_settings)
            gemini_payload = {
                "contents": [{"parts": [{"text": gemini_text}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": gemini_voice
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
                            raise TtsSynthesisError("Gemini TTS audio conversion failed")
                raise TtsSynthesisError("Gemini TTS returned no audio content")
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            # Do not cool the shared key yet: Cloud TTS may still succeed with
            # it, and the pool is also used by the LLM provider.  The key is
            # cooled below only when the fallback fails too.
            logger.warning("Gemini Flash TTS failed; trying Cloud TTS fallback: %s", _redacted_provider_error(exc, keys))
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
