# TTS worker: Piper + FFmpeg + Celery on `tts` (FastAPI health shell — see worker_health.py).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    REPO_ROOT=/app \
    LD_LIBRARY_PATH=/opt/piper \
    PORT=7860 \
    WORKER_HEALTH_MODE=tts

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# rhasspy/piper releases use date tags (not v1.x) and asset names x86_64 / aarch64.
ARG PIPER_RELEASE=2023.11.14-2
RUN set -eux; \
    arch="$(uname -m)"; \
    case "$arch" in \
      aarch64|arm64) asset="piper_linux_aarch64.tar.gz" ;; \
      x86_64|amd64) asset="piper_linux_x86_64.tar.gz" ;; \
      *) echo "unsupported arch for Piper: ${arch}" >&2; exit 1 ;; \
    esac; \
    mkdir -p /opt; \
    curl -fsSL "https://github.com/rhasspy/piper/releases/download/${PIPER_RELEASE}/${asset}" \
      | tar xz -C /opt; \
    test -x /opt/piper/piper

RUN mkdir -p /models \
  && curl -fsSL -o /models/en_US-ryan-medium.onnx \
    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/medium/en_US-ryan-medium.onnx" \
  && curl -fsSL -o /models/en_US-ryan-medium.onnx.json \
    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/medium/en_US-ryan-medium.onnx.json"

WORKDIR /app

COPY pyproject.toml README.md requirements.txt /app/
COPY backend /app/backend
COPY shared /app/shared
COPY worker /app/worker
COPY ai_engine /app/ai_engine
COPY docker/tts-worker/piper.docker.yaml /app/ai_engine/config/piper.local.yaml

RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir -e .

EXPOSE 7860

CMD ["sh", "-c", "exec uvicorn worker.worker_health:app --host 0.0.0.0 --port ${PORT:-7860}"]
