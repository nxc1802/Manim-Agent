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

Copy [`.env.example`](.env.example) to `.env` and adjust when enabling Supabase (Phase 6).

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

### CI/CD — publish to GHCR

Workflow: [`.github/workflows/docker-publish.yml`](.github/workflows/docker-publish.yml) builds & pushes:

- `ghcr.io/<owner>/manim-agent-api:<tag>`
- `ghcr.io/<owner>/manim-agent-worker:<tag>`

Tags: `latest` on `main`, plus `sha-<gitsha>` for traceability.

### Hugging Face Spaces (2 Spaces)

Use **two separate Spaces** so API and worker scale/sleep independently:

1. **Space — API**: Container image = `manim-agent-api` from GHCR. Set secrets/env: `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` (same logical Redis as worker), `PORT` (HF defaults to `7860`; the API Dockerfile respects `PORT`).
2. **Space — Worker**: Container image = `manim-agent-worker` from GHCR. Set the **same** Redis URLs plus Supabase worker vars: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_STORAGE_BUCKET`, optional `SUPABASE_SIGNED_URL_SECONDS`.

Both Spaces must reach the same Redis (for example Upstash) because the API enqueues Celery tasks and the worker consumes them.

### Local image builds

```bash
make docker-build-api
make docker-build-worker
```
