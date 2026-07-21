#!/bin/sh
set -eu

service_name="${1:?service name is required}"
shift

case "$service_name" in
  redis)
    # Redis needs no application configuration. Start it with an allow-listed
    # environment so AOF snapshots and diagnostics cannot expose credentials.
    exec /usr/bin/env -i \
      HOME="${HOME:-/home/user}" \
      PATH=/usr/bin:/bin \
      "$@"
    ;;
  backend)
    # Backend never calls the model provider. Remove every numbered key too.
    for variable_name in $(env | sed 's/=.*//'); do
      case "$variable_name" in
        GOOGLE_API_KEY|GOOGLE_API_KEY_*|GEMINI_API_KEY)
          unset "$variable_name"
          ;;
      esac
    done
    ;;
  ai-worker|render-worker)
    # Workers claim opaque work from Backend and must not receive database keys.
    unset \
      SUPABASE_SECRET_KEY \
      SUPABASE_SERVICE_ROLE_KEY \
      SUPABASE_JWT_SECRET \
      SUPABASE_ACCESS_TOKEN \
      SUPABASE_DB_PASSWORD
    ;;
  *)
    echo "Unknown service profile: $service_name" >&2
    exit 64
    ;;
esac

exec "$@"
