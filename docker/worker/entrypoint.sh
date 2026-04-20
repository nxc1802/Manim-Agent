#!/usr/bin/env bash
# Hugging Face Spaces need HTTP on PORT while Celery has no socket. Keep bash as the
# process group leader (under tini) so the health server and Celery both stay alive.
set -euo pipefail
PORT="${PORT:-7860}"
export PORT
python -m worker.space_health_server &
_health_pid=$!
trap 'kill "${_health_pid}" 2>/dev/null || true' EXIT INT TERM
celery -A worker.celery_app:celery_app worker --loglevel=INFO -Q render
