# Manim Agent

AI-driven pipeline to generate technical Manim videos. Design docs live in [`docs/proposal/`](docs/proposal/).

## Phase 1 — local development

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -U pip
pip install -e ".[dev]"
make dev
```

- API: `http://127.0.0.1:8000/docs`
- Health: `GET /health`, readiness: `GET /ready`
- Stub projects: `GET /v1/projects`

```bash
make test
make lint
make typecheck
```

Copy [`.env.example`](.env.example) to `.env` and set only what you need; all other keys fall back to defaults in [`backend/core/config.py`](backend/core/config.py) (`Settings`).

## Phase 2 — Primitives catalog

- HTTP: `GET /v1/primitives/catalog` (read-only JSON for Builder prompts)
- Library: `primitives/` (lazy-import package; Manim loads on first use)
- Demo scene (requires Manim + system deps such as Cairo/FFmpeg):

```bash
manim -ql examples/demo_primitives_scene.py DemoPrimitivesScene
```

## Phase 3 — Celery + Redis + split Docker images

### Runtime responsibilities

- **API image** ([`docker/api/Dockerfile`](docker/api/Dockerfile)): FastAPI + Celery client only — **no Manim**.
- **Worker image** ([`docker/worker/Dockerfile`](docker/worker/Dockerfile)): Celery consumer + Manim/FFmpeg — **only** renders video, updates **Redis** job state, then (if configured) uploads mp4 to **Supabase Storage** and writes the signed URL into Redis `asset_url`.

### HTTP / queue

- **Queue**: Celery broker + result backend default to `REDIS_URL` (override with `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`).
- **API**:
  - `POST /v1/projects/{project_id}/render` → `202` + `{ "job_id": "...", "status": "queued" }`
  - `GET /v1/jobs/{job_id}` → job snapshot from Redis
- **Worker**: `make worker` (or Docker Compose `worker` service) runs `celery -A worker.celery_app:celery_app worker -Q render`
- **Render**: worker runs `manim render ...` as a subprocess (never inside the API process).

### Local compose

```bash
docker compose up --build
```

Services: `redis`, `api` (port `8000` → container `7860`), `worker`.

### GitHub Actions — deploy Hugging Face Spaces

Single workflow: [`.github/workflows/deploy-hf-spaces.yml`](.github/workflows/deploy-hf-spaces.yml). On **push to `main`** (or manual run), it syncs **three** Space repos (`HF_SPACE_*` variables) with a `Dockerfile` that starts `FROM ghcr.io/<owner>/manim-agent-{api,worker,tts-worker}:<tag>`.

Build and push those images to GHCR yourself (see **Local image builds** below), then set Space **secrets** on Hugging Face (e.g. `REDIS_URL`, Celery URLs, Supabase keys) so containers can run.

### Hugging Face Spaces (3 Spaces)

Use **three** Spaces (API, Manim render worker, TTS worker) so they scale/sleep independently. All must reach the **same** Redis (e.g. Upstash) so the API can enqueue Celery tasks and both workers can consume them.

1. **API** — env: `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `PORT` (defaults `7860`).
2. **Render / TTS workers** — same Redis URLs; optional Supabase for uploads. Worker images run a minimal HTTP server on `PORT` alongside Celery so **Hugging Face Spaces** health checks can reach **Running** (Celery alone does not listen on a port).

### Local image builds

```bash
make docker-build-api
make docker-build-worker
make docker-build-tts-worker
```

Push to GHCR with your registry login, e.g. tag `latest` for `manim-agent-api`, `manim-agent-worker`, and `manim-agent-tts-worker` (see `docker-compose.yml` / `docker/*/Dockerfile` for contexts).
