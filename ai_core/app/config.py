from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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
    celery_broker_url: str | None = Field(default=None, validation_alias="CELERY_BROKER_URL")
    google_api_key: str | None = Field(default=None, validation_alias="GOOGLE_API_KEY")
    default_chat_model: str = Field(
        default="gemini-3-flash-preview", validation_alias="DEFAULT_CHAT_MODEL"
    )
    artifacts_dir: Path = Field(default=Path("/artifacts"), validation_alias="ARTIFACTS_DIR")
    artifact_public_base_url: str | None = Field(
        default=None, validation_alias="ARTIFACT_PUBLIC_BASE_URL"
    )
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

    @property
    def celery_broker_url_resolved(self) -> str:
        return (self.celery_broker_url or self.redis_url).strip()

    @property
    def agent_models_path(self) -> Path:
        return Path(__file__).resolve().parents[1] / "config" / "agent_models.yaml"


settings = Settings()
