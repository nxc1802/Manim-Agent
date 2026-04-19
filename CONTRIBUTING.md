# Contributing to Manim Agent

## Piper TTS (worker)

Synthesis **always** runs Piper in the Celery `tts` worker. Tuning (`binary`, `voice_model_path`, scales) lives in YAML, not env:

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

CI on pull requests runs Ruff, Mypy, unit tests with coverage, integration tests (Redis + Postgres service), and an **E2E** job (`pytest tests/e2e -m e2e`). The live-LLM test **skips** when `OPENROUTER_API_KEY` is unset (fork PRs, local machines without a key) so the workflow stays green.

**Where env vars live:** `.env` / `.env.example` match **`Settings`** in `backend/core/config.py` (runtime API and workers). **Test-only** variables that are *not* in `Settings` — today mainly `POSTGRES_RLS_TEST_URL` — belong in **`tests/.env.test`** (copy from `tests/.env.test.example`); `tests/conftest.py` loads that file before tests if it exists. Shell exports still win over `.env.test` so CI and local overrides behave predictably.

## Hugging Face Spaces + GitHub Actions

You need **one** Hugging Face token plus **three Space repo ids** (use **Variables**, not Secrets, for the ids).

| Kind | Name | Example (this deployment) |
| --- | --- | --- |
| **Secret** | `HF_TOKEN` | HF access token (read enough for verify; write if you automate uploads). |
| **Variable** | `HF_SPACE_API_REPO` | `Cuong2004/Manim-Agent` |
| **Variable** | `HF_SPACE_MANIM_WORKER_REPO` | `Cuong2004/Manim-Agent-Worker-Render` |
| **Variable** | `HF_SPACE_TTS_WORKER_REPO` | `Cuong2004/Manim-Agent-Worker-TTS` |

In GitHub: **Settings → Secrets and variables → Actions**. Put `HF_TOKEN` under **Secrets**; put the three `HF_SPACE_*` values under **Variables** (repository variables are visible to workflows and appear in logs if echoed—avoid putting passwords there; repo ids like `user/space` are fine).

Workflow **Docker images (API + Workers)** pushes images to GHCR. **Hugging Face Spaces** (`.github/workflows/hf-spaces.yml`) runs after that workflow succeeds on `main` (or on manual dispatch) and runs `scripts/hf_verify_spaces.py` to confirm `HF_TOKEN` can read each Space. If `HF_TOKEN` or any repo id is missing, the script skips that check and exits successfully so CI is not blocked until you configure HF.

## E2E with a real LLM (Phase 9)

These tests call your configured provider through **LiteLLM** (same stack as production). They are **skipped** when `OPENROUTER_API_KEY` is missing, so `pytest` without a key stays offline and free.

### Prerequisites

1. **API key** — set `OPENROUTER_API_KEY` for LiteLLM (OpenRouter). Models use the `openrouter/...` ids in `ai_engine/config/agent_models.example.yaml` (or your own `AGENT_MODELS_YAML`).
2. **Redis** — E2E uses the in-process **FakeRedis** from `tests/conftest.py` (no local Redis daemon required for the default E2E test). The GitHub Actions E2E job still starts a **Redis** service container for parity with production settings that expect a broker URL.
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

### CI

Add a repository secret **`OPENROUTER_API_KEY`** on the default branch so the E2E job actually exercises the live LLM instead of skipping. PRs from forks do not receive this secret; those runs skip the live test by design.

### Cost and flakiness

- E2E issues **multiple** LLM calls (planner JSON + builder code). Expect API cost per run.
- Timeouts are set on the E2E test (`pytest-timeout`). Network or rate limits can still fail intermittently; re-run before tagging if needed.

### Audit trail

HTTP requests receive an `X-Request-ID` from `CorrelationIdMiddleware`. For durable audit logs (who changed what), extend the API or mirror events to Postgres in a follow-up; Phase 6+ migrations already support project-scoped tables with RLS.
