from __future__ import annotations

from functools import cached_property
from uuid import UUID

from pydantic import AliasChoices, Field, field_validator, model_validator
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
    supabase_jwt_jwks_url: str | None = Field(
        default=None, validation_alias="SUPABASE_JWT_JWKS_URL"
    )
    supabase_jwt_issuer: str | None = Field(
        default=None, validation_alias="SUPABASE_JWT_ISSUER"
    )
    supabase_jwks_cache_seconds: int = Field(
        default=300,
        ge=30,
        le=600,
        validation_alias="SUPABASE_JWKS_CACHE_SECONDS",
    )
    supabase_jwt_audience: str | None = Field(
        default="authenticated", validation_alias="SUPABASE_JWT_AUDIENCE"
    )

    supabase_url: str | None = Field(default=None, validation_alias="SUPABASE_URL")
    supabase_service_role_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY"),
    )
    supabase_storage_bucket: str = Field(
        default="videos", validation_alias="SUPABASE_STORAGE_BUCKET"
    )
    supabase_signed_url_seconds: int = Field(
        default=3_600,
        ge=60,
        le=86_400,
        validation_alias="SUPABASE_SIGNED_URL_SECONDS",
    )
    internal_render_signed_url_seconds: int = Field(
        default=900, ge=60, le=3_600, validation_alias="INTERNAL_RENDER_SIGNED_URL_SECONDS"
    )

    redis_url: str = Field(default="redis://redis:6379/0", validation_alias="REDIS_URL")
    redis_prefix: str = Field(default="manim", validation_alias="REDIS_PREFIX")
    redis_max_connections: int = Field(default=10, ge=1, validation_alias="REDIS_MAX_CONNECTIONS")
    pipeline_lock_timeout_seconds: int = Field(
        default=300, ge=30, le=1_800, validation_alias="PIPELINE_LOCK_TIMEOUT_SECONDS"
    )
    pipeline_lock_blocking_seconds: int = Field(
        default=10, ge=1, le=60, validation_alias="PIPELINE_LOCK_BLOCKING_SECONDS"
    )
    cache_enabled: bool = Field(default=True, validation_alias="CACHE_ENABLED")
    cache_ttl_seconds: int = Field(default=60, ge=1, validation_alias="CACHE_TTL_SECONDS")
    cache_list_ttl_seconds: int = Field(
        default=30, ge=1, validation_alias="CACHE_LIST_TTL_SECONDS"
    )
    cache_negative_ttl_seconds: int = Field(
        default=5, ge=1, validation_alias="CACHE_NEGATIVE_TTL_SECONDS"
    )
    cache_generation_ttl_seconds: int = Field(
        default=86_400, ge=60, validation_alias="CACHE_GENERATION_TTL_SECONDS"
    )
    websocket_redis_reconnect_max_seconds: float = Field(
        default=5.0, ge=0.1, validation_alias="WEBSOCKET_REDIS_RECONNECT_MAX_SECONDS"
    )
    readiness_cache_seconds: float = Field(
        default=10.0, ge=1.0, validation_alias="READINESS_CACHE_SECONDS"
    )
    readiness_timeout_seconds: float = Field(
        default=2.0, ge=0.1, validation_alias="READINESS_TIMEOUT_SECONDS"
    )
    ai_step_stale_after_seconds: int = Field(
        default=1920, ge=120, validation_alias="AI_STEP_STALE_AFTER_SECONDS"
    )
    ai_step_queue_stale_after_seconds: int = Field(
        default=180, ge=30, validation_alias="AI_STEP_QUEUE_STALE_AFTER_SECONDS"
    )
    celery_broker_url: str | None = Field(default=None, validation_alias="CELERY_BROKER_URL")

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
            if "*" in self.cors_origins_list:
                raise ValueError("CORS_ORIGINS cannot be * outside development")
            if len(self.internal_service_token.strip()) < 32:
                raise ValueError(
                    "INTERNAL_SERVICE_TOKEN must contain at least 32 characters "
                    "outside development"
                )
            if not self.supabase_url or not self.supabase_service_role_key:
                raise ValueError(
                    "SUPABASE_URL and SUPABASE_SECRET_KEY (or legacy service-role key) "
                    "are required outside development"
                )
        return self

    @cached_property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @cached_property
    def celery_broker_url_resolved(self) -> str:
        return (self.celery_broker_url or self.redis_url).strip()

    @cached_property
    def supabase_jwt_issuer_resolved(self) -> str | None:
        configured = (self.supabase_jwt_issuer or "").strip()
        if configured:
            return configured.rstrip("/")
        base = (self.supabase_url or "").strip().rstrip("/")
        return f"{base}/auth/v1" if base else None

    @cached_property
    def supabase_jwt_jwks_url_resolved(self) -> str | None:
        configured = (self.supabase_jwt_jwks_url or "").strip()
        if configured:
            return configured
        issuer = self.supabase_jwt_issuer_resolved
        return f"{issuer}/.well-known/jwks.json" if issuer else None


settings = Settings()
