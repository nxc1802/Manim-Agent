from __future__ import annotations

from functools import cached_property
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration owned by the API service only.

    No provider, Manim, renderer or agent configuration is allowed here. Those
    values belong to ``ai_core`` and are deliberately absent from this model.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = Field(default="development", validation_alias="APP_ENV")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    cors_origins: str = Field(default="http://localhost:5173", validation_alias="CORS_ORIGINS")

    auth_mode: str = Field(default="off", validation_alias="AUTH_MODE")
    dev_default_user_id: UUID = Field(
        default=UUID("00000000-0000-0000-0000-000000000001"),
        validation_alias="DEV_DEFAULT_USER_ID",
    )
    supabase_jwt_secret: str | None = Field(default=None, validation_alias="SUPABASE_JWT_SECRET")
    supabase_jwt_audience: str | None = Field(default="authenticated", validation_alias="SUPABASE_JWT_AUDIENCE")

    supabase_url: str | None = Field(default=None, validation_alias="SUPABASE_URL")
    supabase_anon_key: str | None = Field(default=None, validation_alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str | None = Field(
        default=None, validation_alias="SUPABASE_SERVICE_ROLE_KEY"
    )
    supabase_storage_bucket: str = Field(default="videos", validation_alias="SUPABASE_STORAGE_BUCKET")
    supabase_signed_url_seconds: int = Field(
        default=604_800, validation_alias="SUPABASE_SIGNED_URL_SECONDS"
    )

    redis_url: str = Field(default="redis://redis:6379/0", validation_alias="REDIS_URL")
    redis_prefix: str = Field(default="manim", validation_alias="REDIS_PREFIX")
    redis_max_connections: int = Field(default=10, ge=1, validation_alias="REDIS_MAX_CONNECTIONS")
    celery_broker_url: str | None = Field(default=None, validation_alias="CELERY_BROKER_URL")

    ai_core_url: str = Field(default="http://ai-core:8001", validation_alias="AI_CORE_URL")
    internal_service_token: str = Field(
        default="change-me-in-production", validation_alias="INTERNAL_SERVICE_TOKEN"
    )
    ai_core_step_task: str = Field(
        default="ai_core.generate_hitl_step", validation_alias="AI_CORE_STEP_TASK"
    )
    ai_core_render_task: str = Field(
        default="ai_core.render_manim_scene", validation_alias="AI_CORE_RENDER_TASK"
    )

    sentry_dsn: str | None = Field(default=None, validation_alias="SENTRY_DSN")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def strip_cors(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_production_security(self) -> Settings:
        if self.app_env.lower() in {"production", "prod", "staging"}:
            if self.auth_mode != "jwt":
                raise ValueError("AUTH_MODE must be jwt outside development")
            if self.cors_origins == "*":
                raise ValueError("CORS_ORIGINS cannot be * outside development")
            if self.internal_service_token == "change-me-in-production":
                raise ValueError("INTERNAL_SERVICE_TOKEN must be configured outside development")
        return self

    @cached_property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @cached_property
    def celery_broker_url_resolved(self) -> str:
        return (self.celery_broker_url or self.redis_url).strip()


settings = Settings()
