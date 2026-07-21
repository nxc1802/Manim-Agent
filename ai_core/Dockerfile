FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/srv/ai_core:/srv PORT=8001 ARTIFACTS_DIR=/artifacts

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libcairo2-dev libpango1.0-dev ffmpeg \
    texlive-latex-base texlive-latex-extra texlive-fonts-recommended dvisvgm \
    && rm -rf /var/lib/apt/lists/*

# MathTex/Tex require both a TeX engine and the SVG converter at runtime.
RUN latex --version && dvisvgm --version

WORKDIR /srv/ai_core
COPY ai_core/requirements.lock ./requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock
COPY shared /srv/shared
COPY ai_core/app /srv/ai_core/app
COPY ai_core/config /srv/ai_core/config
RUN useradd --system --create-home --uid 10001 manim \
    && mkdir -p /artifacts \
    && chown -R manim:manim /srv /artifacts
USER manim

EXPOSE 8001
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
