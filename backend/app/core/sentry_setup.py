from __future__ import annotations

import logging

import sentry_sdk

from app.core.config import settings

logger = logging.getLogger(__name__)


def init_sentry() -> None:
    """Initialize Sentry SDK if SENTRY_DSN is configured in settings."""
    if not settings.sentry_dsn:
        logger.info("Sentry DSN not set. Skipping Sentry initialization.")
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        traces_sample_rate=1.0,
    )
    logger.info("Sentry SDK initialized successfully.")
