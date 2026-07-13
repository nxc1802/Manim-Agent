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
    celery_broker_url: str | None = Field(default=None, validation_alias="CELERY_BROKER_URL")
    google_api_key: str | None = Field(default=None, validation_alias="GOOGLE_API_KEY")
    default_chat_model: str = Field(default="gemini-2.5-flash", validation_alias="DEFAULT_CHAT_MODEL")
    artifacts_dir: Path = Field(default=Path("/artifacts"), validation_alias="ARTIFACTS_DIR")
    artifact_public_base_url: str | None = Field(default=None, validation_alias="ARTIFACT_PUBLIC_BASE_URL")
    manim_timeout_seconds: int = Field(default=3600, validation_alias="MANIM_TIMEOUT_SECONDS")
    review_loop_final_tier_max_attempts: int = Field(
        default=2, validation_alias="REVIEW_LOOP_MAX_ATTEMPTS",
    )
    review_render_quality: str = Field(
        default="-ql", validation_alias="REVIEW_RENDER_QUALITY",
    )
    review_render_timeout: int = Field(
        default=120, validation_alias="REVIEW_RENDER_TIMEOUT",
    )

    @property
    def celery_broker_url_resolved(self) -> str:
        return (self.celery_broker_url or self.redis_url).strip()

    @property
    def agent_models_path(self) -> Path:
        return Path(__file__).resolve().parents[1] / "config" / "agent_models.yaml"


settings = Settings()
