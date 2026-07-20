# Manim Agent

Manim Agent is now split into two independent services:

- `backend/` — FastAPI, authentication, Supabase/Postgres persistence, durable HITL approvals, WebSocket gateway and Redis task dispatch.
- `ai_core/` — Google LLM runtime, token streaming, safe Manim validation and rendering workers.
- `shared/` — small Pydantic contracts only; it has no service or database logic.

The Backend never imports LLM, Manim or worker code. AI Core never imports Backend code or has database credentials. They communicate with authenticated internal HTTP and Redis/Celery queues.

## Start locally

```bash
cp backend/.env.example backend/.env
cp ai_core/.env.example ai_core/.env
cp frontend/.env.example frontend/.env
# fill Supabase values in backend/.env and Google API keys in ai_core/.env
docker compose up --build
```

Compose starts Redis, Backend, the private AI Core API, and the AI worker. Start the browser app separately:

```bash
cd frontend && npm install && npm run dev
```

Backend is available at `http://localhost:8000/docs`; AI Core remains private to Compose. Apply every file in `backend/supabase/migrations/` in lexical order before the first real HITL run. For production set `AUTH_MODE=jwt`, configure the Supabase JWT secret in Backend only, and put `VITE_SUPABASE_URL` plus the publishable/anon key in `frontend/.env`. For a local Redis-only UI/API session, set `VITE_AUTH_MODE=off` and `AUTH_MODE=off`; durable HITL still requires Supabase.

## Development

```bash
make install-be install-ai
make dev-be       # terminal 1
make dev-ai       # terminal 2
make worker-ai    # terminal 3
make dev-fe       # terminal 4
```

Run service checks independently with `make test-be`, `make test-ai`, and `make test-fe`. `GET /health` is a liveness check; `GET /ready` reports dependency readiness for Backend and AI Core.

Read [architecture](docs/ARCHITECTURE.md) before changing boundaries, and use the [Frontend API reference](docs/FRONTEND_API.md) as the public API contract.
