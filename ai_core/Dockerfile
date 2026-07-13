FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/srv/ai_core:/srv PORT=8001 ARTIFACTS_DIR=/artifacts

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libcairo2-dev libpango1.0-dev ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/ai_core
COPY ai_core/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY shared /srv/shared
COPY ai_core/app /srv/ai_core/app
COPY ai_core/config /srv/ai_core/config

EXPOSE 8001
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
