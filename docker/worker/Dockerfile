# Worker image: Manim + FFmpeg + Celery consumer only (no FastAPI server).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    REPO_ROOT=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libcairo2-dev \
    libpango1.0-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md requirements.txt /app/
COPY backend /app/backend
COPY shared /app/shared
COPY primitives /app/primitives
COPY worker /app/worker
COPY examples /app/examples
COPY docs /app/docs
COPY ai_engine /app/ai_engine

RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir -e ".[worker]"

CMD ["celery", "-A", "worker.celery_app:celery_app", "worker", "--loglevel=INFO", "-Q", "render"]
