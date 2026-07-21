FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b AS python-dependencies

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libcairo2-dev \
    libpango1.0-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY backend/requirements.lock ./backend-requirements.lock
COPY ai_core/requirements.lock ./ai-core-requirements.lock
# Backend and AI intentionally use isolated environments: their fully resolved
# locks can pin different versions of a transitive dependency (currently Redis).
RUN python -m venv /opt/backend-venv \
    && /opt/backend-venv/bin/pip install --no-cache-dir --require-hashes \
        -r backend-requirements.lock
RUN python -m venv /opt/ai-venv \
    && /opt/ai-venv/bin/pip install --no-cache-dir --require-hashes \
        -r ai-core-requirements.lock


FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b AS runtime

LABEL org.opencontainers.image.title="Manim Agent - Hugging Face single Space" \
      org.opencontainers.image.description="Trusted-input API, AI and render runtime; frontend deploys on Vercel"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    APP_ENV=production \
    CORS_ORIGINS= \
    REDIS_URL=redis://127.0.0.1:6379/0 \
    CELERY_BROKER_URL=redis://127.0.0.1:6379/0 \
    BACKEND_INTERNAL_URL=http://127.0.0.1:7860/internal \
    ARTIFACTS_DIR=/artifacts \
    REDIS_DATA_DIR=/data/redis \
    DEPLOYMENT_PROFILE=hf-single-space-trusted-input \
    HOME=/home/user

RUN apt-get update && apt-get install -y --no-install-recommends \
    dvisvgm \
    ffmpeg \
    fonts-dejavu-core \
    libgl1 \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    redis-server \
    supervisor \
    texlive-fonts-recommended \
    texlive-latex-base \
    texlive-latex-extra \
    tini \
    && rm -rf /var/lib/apt/lists/* \
    && latex --version \
    && dvisvgm --version

COPY --from=python-dependencies /opt/backend-venv /opt/backend-venv
COPY --from=python-dependencies /opt/ai-venv /opt/ai-venv

RUN groupadd --gid 1000 user \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh user \
    && mkdir -p /srv/backend /srv/ai_core /srv/shared /srv/deploy \
        /artifacts /data/redis /tmp/supervisor \
    && chown -R user:user /artifacts /data /tmp/supervisor

COPY backend/app /srv/backend/app
COPY ai_core/app /srv/ai_core/app
COPY ai_core/config /srv/ai_core/config
COPY shared /srv/shared
COPY deploy/huggingface/supervisord.conf /srv/deploy/supervisord.conf
COPY deploy/huggingface/redis.conf /srv/deploy/redis.conf
COPY deploy/huggingface/entrypoint.sh /srv/deploy/entrypoint.sh
COPY deploy/huggingface/service-entrypoint.sh /srv/deploy/service-entrypoint.sh
COPY deploy/huggingface/healthcheck.sh /srv/deploy/healthcheck.sh
RUN chmod 0755 \
    /srv/deploy/entrypoint.sh \
    /srv/deploy/service-entrypoint.sh \
    /srv/deploy/healthcheck.sh

USER user
WORKDIR /home/user

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD ["/srv/deploy/healthcheck.sh"]

ENTRYPOINT ["/usr/bin/tini", "--", "/srv/deploy/entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-c", "/srv/deploy/supervisord.conf"]
