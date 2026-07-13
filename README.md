# Manim Agent

Manim Agent is now split into two independent services:

- `backend/` — FastAPI, authentication, Supabase/Postgres persistence, durable HITL approvals, WebSocket gateway and Redis task dispatch.
- `ai_core/` — Google LLM runtime, token streaming, safe Manim validation and rendering workers.
- `shared/` — small Pydantic contracts only; it has no service or database logic.

The Backend never imports LLM, Manim or worker code. AI Core never imports Backend code or has database credentials. They communicate with authenticated internal HTTP and Redis/Celery queues.

## Start locally

```bash
cp backend/.env.example backend/.backend.env
cp ai_core/.env.example ai_core/.ai_core.env
# fill Supabase values in backend/.backend.env and Google API keys in ai_core/.ai_core.env
docker compose up --build
```

Backend is available at `http://localhost:8000/docs`; AI Core is private to Compose. Apply `backend/supabase/migrations/20260712000000_hitl_steps.sql` after the existing Supabase migrations.

## Development

```bash
make install-be install-ai
make dev-be       # terminal 1
make dev-ai       # terminal 2
make worker-ai    # terminal 3
```

Read [architecture](docs/ARCHITECTURE.md) before changing boundaries, and use the [Frontend API reference](docs/FRONTEND_API.md) as the public API contract.
