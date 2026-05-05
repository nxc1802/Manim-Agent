from __future__ import annotations

from functools import cached_property
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment (and optional `.env`)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", validation_alias="APP_ENV")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    cors_origins: str = Field(default="", validation_alias="CORS_ORIGINS")

    dev_default_user_id: UUID = Field(
        default=UUID("00000000-0000-0000-0000-000000000001"),
        validation_alias="DEV_DEFAULT_USER_ID",
    )
    openrouter_api_key: str | None = Field(default=None, validation_alias="OPENROUTER_API_KEY")
    llm_api_base: str = Field(
        default="https://openrouter.ai/api/v1",
        validation_alias="LLM_API_BASE",
    )
    dashscope_api_key: str | None = Field(default=None, validation_alias="DASHSCOPE_API_KEY")
    agent_models_yaml: str | None = Field(default=None, validation_alias="AGENT_MODELS_YAML")
    default_agent_model: str = Field(
        default="openrouter/google/gemma-4-31b-it:free",
        validation_alias="DEFAULT_AGENT_MODEL",
    )

    auth_mode: Literal["off", "jwt"] = Field(default="off", validation_alias="AUTH_MODE")
    supabase_jwt_secret: str | None = Field(default=None, validation_alias="SUPABASE_JWT_SECRET")
    supabase_jwt_audience: str | None = Field(
        default="authenticated",
        validation_alias="SUPABASE_JWT_AUDIENCE",
    )

    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    redis_prefix: str = Field(default="manim_agent", validation_alias="REDIS_PREFIX")
    celery_broker_url: str | None = Field(default=None, validation_alias="CELERY_BROKER_URL")
    celery_result_backend: str | None = Field(
        default=None,
        validation_alias="CELERY_RESULT_BACKEND",
    )

    manim_scene_file: str = Field(
        default="examples/demo_primitives_scene.py",
        validation_alias="MANIM_SCENE_FILE",
    )
    manim_scene_class: str = Field(
        default="DemoPrimitivesScene",
        validation_alias="MANIM_SCENE_CLASS",
    )
    storage_dir: str = Field(default="storage", validation_alias="STORAGE_DIR")
    output_dir: str = Field(default="storage/outputs", validation_alias="OUTPUT_DIR")
    repo_root: str = Field(default=".", validation_alias="REPO_ROOT")
    generated_scene_class: str = Field(
        default="GeneratedScene",
        validation_alias="GENERATED_SCENE_CLASS",
    )
    max_manim_code_bytes: int = Field(
        default=200_000,
        validation_alias="MAX_MANIM_CODE_BYTES",
    )

    worker_name: str = Field(default="manim-worker", validation_alias="WORKER_NAME")
    worker_image_tag: str | None = Field(default=None, validation_alias="WORKER_IMAGE_TAG")
    tts_worker_name: str = Field(default="manim-agent-tts", validation_alias="TTS_WORKER_NAME")
    tts_worker_image_tag: str | None = Field(default=None, validation_alias="TTS_WORKER_IMAGE_TAG")

    supabase_url: str | None = Field(default=None, validation_alias="SUPABASE_URL")
    supabase_anon_key: str | None = Field(default=None, validation_alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str | None = Field(
        default=None,
        validation_alias="SUPABASE_SERVICE_ROLE_KEY",
    )
    supabase_storage_bucket: str = Field(
        default="videos",
        validation_alias="SUPABASE_STORAGE_BUCKET",
    )
    supabase_signed_url_seconds: int = Field(
        default=604_800,
        validation_alias="SUPABASE_SIGNED_URL_SECONDS",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def strip_cors(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @model_validator(mode="after")
    def validate_production_security(self) -> Settings:
        # Guard against AUTH_MODE=off in production
        is_prod = self.app_env.lower() in ("production", "prod", "staging")
        if is_prod and self.auth_mode == "off":
            msg = f"AUTH_MODE cannot be 'off' when APP_ENV is '{self.app_env}'. Set AUTH_MODE=jwt."
            raise ValueError(msg)

        # Guard against wildcard CORS in production
        if is_prod and self.cors_origins == "*":
            msg = (
                f"CRITICAL SECURITY ERROR: CORS_ORIGINS cannot be '*' "
                f"when APP_ENV is '{self.app_env}'. "
                "Set specific allowed domains for production."
            )
            raise ValueError(msg)
        return self

    @cached_property
    def cors_origins_list(self) -> list[str]:
        if not self.cors_origins:
            return []
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @cached_property
    def celery_broker_url_resolved(self) -> str:
        return (self.celery_broker_url or self.redis_url).strip()

    @cached_property
    def celery_result_backend_resolved(self) -> str:
        return (self.celery_result_backend or self.redis_url).strip()


settings = Settings()
