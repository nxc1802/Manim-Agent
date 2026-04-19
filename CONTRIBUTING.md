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
| `pytest tests/integration -q -m integration` | Postgres RLS checks (`POSTGRES_RLS_TEST_URL` required) |
| `make test-e2e-llm` | **Real LLM** E2E (`tests/e2e`, see below) |
| `pytest tests -m "not e2e_llm"` | Full tree except E2E (avoids skip noise in local runs) |

CI on pull requests runs Ruff, Mypy, unit tests with coverage, and integration tests (Redis + Postgres service).

## E2E with a real LLM (Phase 9)

These tests call your configured provider through **LiteLLM** (same stack as production). They are **skipped** unless you opt in, so normal `pytest` runs stay offline and free.

### Prerequisites

1. **API key** — set `OPENROUTER_API_KEY` for LiteLLM (OpenRouter). Models use the `openrouter/...` ids in `ai_engine/config/agent_models.example.yaml` (or your own `AGENT_MODELS_YAML`).
2. **Opt-in flag** — set `E2E_LLM=1` so accidental full-suite runs do not bill your account.
3. **Redis** — E2E uses the in-process **FakeRedis** from `tests/conftest.py` (no local Redis daemon required for the default E2E test).
4. **Models** — override `AGENT_MODELS_YAML` if you want cheaper or pinned models for release runs.

### Run locally

```bash
export E2E_LLM=1
export OPENROUTER_API_KEY="sk-or-..."
# optional: export AGENT_MODELS_YAML="$PWD/agent_models.yaml"
make test-e2e-llm
```

Equivalent:

```bash
E2E_LLM=1 OPENROUTER_API_KEY="sk-or-..." pytest tests/e2e -m e2e_llm -q --tb=short
```

### CI / release

Workflow **Release gate (E2E LLM)** (`.github/workflows/release-gate.yml`) runs on:

- `git push` of tags matching `v*`
- manual **workflow_dispatch**

Add a repository secret named **`OPENROUTER_API_KEY`**. If the secret is missing while `CI=true` and `E2E_LLM=1`, the gate **fails** (it does not silently skip).

### Cost and flakiness

- E2E issues **multiple** LLM calls (planner JSON + builder code). Expect API cost per run.
- Timeouts are set on the E2E test (`pytest-timeout`). Network or rate limits can still fail intermittently; re-run before tagging if needed.

### Audit trail

HTTP requests receive an `X-Request-ID` from `CorrelationIdMiddleware`. For durable audit logs (who changed what), extend the API or mirror events to Postgres in a follow-up; Phase 6+ migrations already support project-scoped tables with RLS.
