# AI Core

AI Core owns provider calls, prompt execution, review-loop repair, TTS, Manim validation/render and Celery tasks. It receives work by opaque ID, claims details from Backend and returns results through authenticated internal callbacks. It must not receive Supabase/database credentials.

## Local

```bash
cp .env.example .env
make install
make lint
make test
make dev       # readiness-only HTTP service
make worker    # combined local worker; Compose separates ai/render queues
```

Required for real generation: Redis, `BACKEND_INTERNAL_URL`, matching `INTERNAL_SERVICE_TOKEN`, and one or more Google API keys. The production token must contain at least 32 random characters. Production workers use concurrency/prefetch 1, task time limits and child recycling. Render output is staged in `ARTIFACTS_DIR`; Backend owns durable Storage upload.

Generated Manim code is trusted-input only. Read [../SECURITY.md](../SECURITY.md) before changing validation or deployment isolation.
