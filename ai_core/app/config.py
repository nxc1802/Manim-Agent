from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = Field(default="development", validation_alias="APP_ENV")
    backend_internal_url: str = Field(
        default="http://backend:8000/internal", validation_alias="BACKEND_INTERNAL_URL"
    )
    internal_service_token: str = Field(
        default="change-me-in-production", validation_alias="INTERNAL_SERVICE_TOKEN"
    )
    redis_url: str = Field(default="redis://redis:6379/0", validation_alias="REDIS_URL")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    readiness_timeout_seconds: float = Field(
        default=3.0, gt=0, validation_alias="READINESS_TIMEOUT_SECONDS"
    )
    ai_step_soft_time_limit_seconds: int = Field(
        default=1800, ge=60, validation_alias="AI_STEP_SOFT_TIME_LIMIT_SECONDS"
    )
    ai_step_time_limit_seconds: int = Field(
        default=1890, ge=61, validation_alias="AI_STEP_TIME_LIMIT_SECONDS"
    )
    render_soft_time_limit_seconds: int = Field(
        default=3900, ge=120, validation_alias="RENDER_SOFT_TIME_LIMIT_SECONDS"
    )
    render_time_limit_seconds: int = Field(
        default=4000, ge=121, validation_alias="RENDER_TIME_LIMIT_SECONDS"
    )
    celery_visibility_timeout_seconds: int = Field(
        default=7200, ge=300, validation_alias="CELERY_VISIBILITY_TIMEOUT_SECONDS"
    )
    celery_max_tasks_per_child: int = Field(
        default=10, ge=1, validation_alias="CELERY_MAX_TASKS_PER_CHILD"
    )
    celery_broker_url: str | None = Field(default=None, validation_alias="CELERY_BROKER_URL")
    google_api_key: str | None = Field(default=None, validation_alias="GOOGLE_API_KEY")
    default_chat_model: str = Field(
        default="gemini-3.5-flash", validation_alias="DEFAULT_CHAT_MODEL"
    )
    artifacts_dir: Path = Field(default=Path("/artifacts"), validation_alias="ARTIFACTS_DIR")
    manim_timeout_seconds: int = Field(default=3600, validation_alias="MANIM_TIMEOUT_SECONDS")
    tts_timeout_seconds: int = Field(default=120, ge=1, validation_alias="TTS_TIMEOUT_SECONDS")
    concat_download_timeout_seconds: int = Field(
        default=120, ge=1, validation_alias="CONCAT_DOWNLOAD_TIMEOUT_SECONDS"
    )
    concat_source_max_bytes: int = Field(
        default=1_073_741_824, ge=1, validation_alias="CONCAT_SOURCE_MAX_BYTES"
    )
    review_loop_final_tier_max_attempts: int = Field(
        default=3,
        validation_alias="REVIEW_LOOP_MAX_ATTEMPTS",
    )
    review_render_quality: str = Field(
        default="-ql",
        validation_alias="REVIEW_RENDER_QUALITY",
    )
    review_render_timeout: int = Field(
        default=120,
        validation_alias="REVIEW_RENDER_TIMEOUT",
    )
    manim_memory_limit_mb: int = Field(default=2048, validation_alias="MANIM_MEMORY_LIMIT_MB")
    manim_cpu_limit_seconds: int = Field(default=300, validation_alias="MANIM_CPU_LIMIT_SECONDS")

    @model_validator(mode="after")
    def validate_runtime_limits(self) -> Settings:
        if self.ai_step_time_limit_seconds <= self.ai_step_soft_time_limit_seconds:
            raise ValueError("AI_STEP_TIME_LIMIT_SECONDS must exceed its soft limit")
        if self.render_time_limit_seconds <= self.render_soft_time_limit_seconds:
            raise ValueError("RENDER_TIME_LIMIT_SECONDS must exceed its soft limit")
        if self.render_soft_time_limit_seconds <= self.manim_timeout_seconds:
            raise ValueError("RENDER_SOFT_TIME_LIMIT_SECONDS must exceed MANIM_TIMEOUT_SECONDS")
        if self.celery_visibility_timeout_seconds <= self.render_time_limit_seconds:
            raise ValueError("CELERY_VISIBILITY_TIMEOUT_SECONDS must exceed render hard limit")
        if self.app_env.lower() in {"production", "prod", "staging"}:
            if len(self.internal_service_token.strip()) < 32:
                raise ValueError(
                    "INTERNAL_SERVICE_TOKEN must contain at least 32 characters "
                    "outside development"
                )
            if not self.backend_internal_url.startswith(("http://", "https://")):
                raise ValueError("BACKEND_INTERNAL_URL must be an HTTP(S) URL")
            has_provider_key = bool(
                self.google_api_key
                or os.getenv("GEMINI_API_KEY")
                or any(
                    value
                    for name, value in os.environ.items()
                    if name.startswith("GOOGLE_API_KEY_")
                    and name.removeprefix("GOOGLE_API_KEY_").isdigit()
                )
            )
            if not has_provider_key:
                raise ValueError("At least one Google provider key is required outside development")
        return self

    @property
    def celery_broker_url_resolved(self) -> str:
        return (self.celery_broker_url or self.redis_url).strip()

    @property
    def agent_models_path(self) -> Path:
        return Path(__file__).resolve().parents[1] / "config" / "agent_models.yaml"


settings = Settings()
