#!/bin/sh
set -eu

case "${APP_ENV:-development}" in
  production|prod|staging)
    if [ "${AUTH_MODE:-}" != "jwt" ]; then
      echo "AUTH_MODE must be jwt outside development" >&2
      exit 1
    fi
    internal_service_token="${INTERNAL_SERVICE_TOKEN:-}"
    if [ "${#internal_service_token}" -lt 32 ]; then
      echo "INTERNAL_SERVICE_TOKEN must contain at least 32 characters outside development" >&2
      exit 1
    fi
    if [ -z "${SUPABASE_URL:-}" ]; then
      echo "SUPABASE_URL must be configured outside development" >&2
      exit 1
    fi
    if [ -z "${SUPABASE_SECRET_KEY:-${SUPABASE_SERVICE_ROLE_KEY:-}}" ]; then
      echo "SUPABASE_SECRET_KEY (or legacy service-role key) is required" >&2
      exit 1
    fi
    if [ -z "${CORS_ORIGINS:-}" ]; then
      echo "CORS_ORIGINS must contain the Vercel production origin" >&2
      exit 1
    fi
    if [ -z "${GOOGLE_API_KEY:-${GEMINI_API_KEY:-}}" ] && \
       ! env | grep -Eq '^GOOGLE_API_KEY_[0-9]+=.+$'; then
      echo "At least one Google provider key must be configured" >&2
      exit 1
    fi
    ;;
esac

# A paid Space storage volume may replace /data at runtime, so create the Redis
# subdirectory after mounts have been attached. Hugging Face runs this image as
# UID 1000, which also owns /artifacts in the image.
mkdir -p \
  "${REDIS_DATA_DIR:-/data/redis}" \
  "${ARTIFACTS_DIR:-/artifacts}" \
  /tmp/supervisor

exec "$@"
