#!/usr/bin/env bash
set -euo pipefail
PORT="${PORT:-7860}"
export PORT
python -m worker.space_health_server &
exec celery -A worker.celery_app:celery_app worker --loglevel=INFO -Q tts -n "tts@%h"
