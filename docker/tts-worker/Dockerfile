# TTS worker: Piper + FFmpeg + Celery consumer on the `tts` queue (no Manim).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    REPO_ROOT=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ARG PIPER_VERSION=1.2.0
RUN set -eux; \
    arch="$(uname -m)"; \
    case "$arch" in \
      aarch64|arm64) parch="arm64" ;; \
      *) parch="amd64" ;; \
    esac; \
    curl -fsSL "https://github.com/rhasspy/piper/releases/download/v${PIPER_VERSION}/piper_linux_${parch}.tar.gz" \
      | tar xz -C /usr/local/bin --strip-components=1 piper/piper

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

CMD ["celery", "-A", "worker.celery_app:celery_app", "worker", "--loglevel=INFO", "-Q", "tts", "-n", "tts@%h"]
