#!/usr/bin/env bash
# See docker/worker/entrypoint.sh — HF probes PORT; Celery stays foreground under tini.
set -euo pipefail
PORT="${PORT:-7860}"
export PORT
python -m worker.space_health_server &
_health_pid=$!
trap 'kill "${_health_pid}" 2>/dev/null || true' EXIT INT TERM
celery -A worker.celery_app:celery_app worker --loglevel=INFO -Q tts -n "tts@%h"
