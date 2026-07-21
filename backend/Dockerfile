FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 PYTHONPATH=/srv/backend:/srv
WORKDIR /srv/backend

COPY backend/requirements.lock ./requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock

COPY shared /srv/shared
COPY backend/app /srv/backend/app

RUN useradd --system --create-home --uid 10001 backend \
    && chown -R backend:backend /srv
USER backend

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
