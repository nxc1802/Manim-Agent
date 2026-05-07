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
- Health: `GET /health`, readiness: `GET /ready` (`503` when Redis is unreachable)
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

Single workflow: [`.github/workflows/deploy-hf-spaces.yml`](.github/workflows/deploy-hf-spaces.yml). On **push to `main`** (or manual run), each Space receives a **source slice** of this monorepo (e.g. `backend/`, `shared/`, `worker/`, `ai_engine/`, plus `primitives/` / `examples/` / `docs/` where the Dockerfile needs them) and the correct **`docker/*/Dockerfile` copied to `./Dockerfile`**, then [`scripts/push_hf_space.sh`](scripts/push_hf_space.sh) runs **`git push --force`** to the Hugging Face Space (`HF_TOKEN` + `HF_SPACE_*`). Hugging Face **builds the image on the Space** — no GHCR-only thin image. Worker Spaces use **FastAPI** on `PORT` in [`worker/worker_health.py`](worker/worker_health.py) so the runtime shows **Running**.

Set Space **secrets** on Hugging Face (e.g. `REDIS_URL`, Celery URLs, Supabase keys) so each build can run. **Local image builds** below are optional (compose / your own registry), not part of the HF deploy path.

### Hugging Face Spaces (3 Spaces)

Use **three** Spaces (API, Manim render worker, TTS worker) so they scale/sleep independently. All must reach the **same** Redis (e.g. Upstash) so the API can enqueue Celery tasks and both workers can consume them.

1. **API** — env: `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `PORT` (defaults `7860`).
2. **Render / TTS workers** — same Redis URLs; optional Supabase for uploads. Worker images run **[`worker/worker_health.py`](worker/worker_health.py)**: **FastAPI** on `PORT` (health JSON) and **Celery** as a subprocess in the app lifespan (`WORKER_HEALTH_MODE=render` or `tts`, `--concurrency=1`) so platforms like **Hugging Face Spaces** see an HTTP listener while tasks run.

### Local image builds

```bash
make docker-build-api
make docker-build-worker
make docker-build-tts-worker
```

To publish elsewhere, tag and push with your registry login (see `docker-compose.yml` / `docker/*/Dockerfile` for build contexts).
