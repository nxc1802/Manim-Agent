# Contributing to Manim Agent

## Piper TTS (worker)

Synthesis **always** runs Piper in the Celery `tts` worker. On **Docker / Hugging Face**, the container entry is **`worker.worker_health`**: FastAPI keeps `PORT` open for health checks and starts Celery in `lifespan` (`WORKER_HEALTH_MODE=tts` in the TTS image).

Tuning (`binary`, `voice_model_path`, scales) lives in YAML, not env:

- Defaults: `ai_engine/config/piper.example.yaml`
- Overrides: copy to `ai_engine/config/piper.local.yaml` (gitignored). The Docker TTS image bakes `docker/tts-worker/piper.docker.yaml` as `piper.local.yaml`.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

Run the API locally (Redis required for `/ready`):

```bash
# Terminal 1
redis-server

# Terminal 2
make dev
```

## Tests

| Command | Purpose |
| --- | --- |
| `make test` | Fast unit tests (`tests/unit`), no network |
| `pytest tests/integration -q -m integration` | Postgres RLS checks — set `POSTGRES_RLS_TEST_URL` (see `tests/.env.test.example`) |
| `make test-e2e` | **Real LLM** E2E (`tests/e2e`, see below) |
| `pytest tests -m "not e2e"` | Full tree except E2E (avoids skip noise in local runs) |

**GitHub Actions** in this repo only **deploys the three Hugging Face Spaces** (see below). Run **lint / typecheck / tests locally** before you push (`make lint`, `make typecheck`, `make test`, integration/E2E as needed).

**Where env vars live:** `.env` / `.env.example` match **`Settings`** in `backend/core/config.py` (runtime API and workers). **Test-only** variables that are *not* in `Settings` — today mainly `POSTGRES_RLS_TEST_URL` — belong in **`tests/.env.test`** (copy from `tests/.env.test.example`); `tests/conftest.py` loads that file before tests if it exists. Shell exports still win over `.env.test`.

## Hugging Face Spaces + GitHub Actions

The only workflow is [`.github/workflows/deploy-hf-spaces.yml`](.github/workflows/deploy-hf-spaces.yml): **exactly three jobs** (API, Render worker, TTS worker) — no separate “changes” job; each job runs its own path filter. On **push to `main`**, a job **skips** the Hugging Face sync when its paths did not change. **workflow_dispatch** deploys **all three** Spaces (each job runs the sync). Space commits are tagged `[API]` / `[Render]` / `[TTS]` with SHA and run id. `scripts/sync_hf_spaces.py` uses **`HF_SYNC_TARGET`** for a single Space per job.

You need **one** Hugging Face token plus **three Space repo ids** (use **Variables** for the ids).

| Kind | Name | Example (this deployment) |
| --- | --- | --- |
| **Secret** | `HF_TOKEN` | HF token with **write** access to all three Spaces. |
| **Variable** | `HF_SPACE_API_REPO` | `Cuong2004/Manim-Agent` |
| **Variable** | `HF_SPACE_MANIM_WORKER_REPO` | `Cuong2004/Manim-Agent-Worker-Render` |
| **Variable** | `HF_SPACE_TTS_WORKER_REPO` | `Cuong2004/Manim-Agent-Worker-TTS` |
| **Variable** (optional) | `HF_IMAGE_TAG` | Image tag on GHCR (default **`latest`** if unset). |

In GitHub: **Settings → Secrets and variables → Actions**. Put `HF_TOKEN` under **Secrets**; put the three `HF_SPACE_*` values under **Variables**.

**GHCR images:** this repo no longer builds them in Actions. Build and push locally or with your own pipeline, e.g. `docker build` / `docker push` to `ghcr.io/<owner>/manim-agent-api`, `manim-agent-worker`, `manim-agent-tts-worker` with tag `latest` (or set `HF_IMAGE_TAG` to match).

## E2E with a real LLM (Phase 9)

These tests call your configured provider through **LiteLLM** (same stack as production). They are **skipped** when `OPENROUTER_API_KEY` is missing, so `pytest` without a key stays offline and free.

### Prerequisites

1. **API key** — set `OPENROUTER_API_KEY` for LiteLLM (OpenRouter). Models use the `openrouter/...` ids in `ai_engine/config/agent_models.example.yaml` (or your own `AGENT_MODELS_YAML`).
2. **Redis** — E2E uses the in-process **FakeRedis** from `tests/conftest.py` (no local Redis daemon required for the default E2E test).
3. **Models** — override `AGENT_MODELS_YAML` if you want cheaper or pinned models for release runs.

### Run locally

```bash
export OPENROUTER_API_KEY="sk-or-..."
# optional: export AGENT_MODELS_YAML="$PWD/agent_models.yaml"
make test-e2e
```

Equivalent:

```bash
OPENROUTER_API_KEY="sk-or-..." pytest tests/e2e -m e2e -q --tb=short
```

### Cost and flakiness

- E2E issues **multiple** LLM calls (planner JSON + builder code). Expect API cost per run.
- Timeouts are set on the E2E test (`pytest-timeout`). Network or rate limits can still fail intermittently; re-run before tagging if needed.

### Audit trail

HTTP requests receive an `X-Request-ID` from `CorrelationIdMiddleware`. For durable audit logs (who changed what), extend the API or mirror events to Postgres in a follow-up; Phase 6+ migrations already support project-scoped tables with RLS.
