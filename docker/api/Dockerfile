# API image: FastAPI + Celery client only (no Manim / no Cairo stack).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=7860

WORKDIR /app

COPY pyproject.toml README.md requirements.txt /app/
COPY backend /app/backend
COPY shared /app/shared
COPY primitives /app/primitives
COPY worker /app/worker
COPY ai_engine /app/ai_engine

RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir -e .

EXPOSE 7860

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
