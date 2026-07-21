# Backend

Fast API owns browser/API authorization, tenant checks, projects/scenes/settings, durable HITL state, Redis cache/events/jobs, task dispatch and Supabase Storage upload/signing. It must not import LLM, Manim or AI Core implementation.

## Local

```bash
cp .env.example .env
make install
make lint
make test
make dev
```

Production uses `AUTH_MODE=jwt`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY` (or legacy service-role alias), an `INTERNAL_SERVICE_TOKEN` of at least 32 random characters, and Redis. JWT JWKS URL/issuer are derived from `SUPABASE_URL` unless overridden.

`GET /health` is liveness. `GET /ready` verifies Redis and Supabase. Worker callbacks live below `/internal` and require `X-Internal-Token`; they are excluded from OpenAPI.

Schema instructions: [supabase/README.md](supabase/README.md). Public API contract: [../docs/FRONTEND_API.md](../docs/FRONTEND_API.md).
