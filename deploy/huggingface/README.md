---
title: Manim Agent
emoji: 🎬
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
---

# Hugging Face single-Space deployment

This deployment profile runs the React application, FastAPI Backend, an
embedded Redis instance, and separate `ai` and `render` Celery workers in one
Docker Space. Supervisor keeps the four processes alive and stops the render
worker, AI worker, Backend, and Redis in reverse priority order.

## Security boundary

This profile is production-configured but intentionally **single-tenant and
trusted-input only**. Generated or edited Manim Python executes in the same
container that holds service credentials. AST validation and a sanitized child
environment reduce accidental misuse; they are not a security sandbox. Do not
offer this profile as a public multi-tenant code-execution service.

The hardening path is to split the Web/API, AI, and render runtimes. All Manim
validation and final rendering should then run in an ephemeral sandbox/job with
no provider or database credentials, a one-time claim token, and a presigned
artifact upload URL.

## Space setup

Create a protected or private Docker Space and deploy the repository with the
root `Dockerfile`. Port `7860` is the only public port. API calls use `/v1` and
WebSockets use `/v1/ws`; the React SPA is served at `/`, so no cross-origin API
configuration is required.

Use paid always-on hardware and attach persistent storage at `/data` for the
supported production profile. Queue, lock, and render-job coordination live in
Redis AOF; without persistent `/data`, the deployment is a non-durable
demo/staging profile and queued work can be lost on restart. Rendered files are
staged under `/artifacts` and are uploaded to Supabase Storage by the Backend.

Set these public Space build Variables:

- `VITE_AUTH_MODE=jwt`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_PUBLISHABLE_KEY`
- Leave `VITE_API_BASE_URL` and `VITE_WS_BASE_URL` empty for same-origin routing.

Set these runtime Secrets:

- `SUPABASE_SECRET_KEY` (`SUPABASE_SERVICE_ROLE_KEY` remains a legacy alias).
- `SUPABASE_JWT_SECRET` only while legacy HS256 tokens are still enabled.
- `INTERNAL_SERVICE_TOKEN` — a long random value, shared internally by the
  Backend and both workers in this single container.
- `GOOGLE_API_KEY` or the numbered Google key pool variables.

Optional runtime Variables include `SUPABASE_STORAGE_BUCKET`, `LOG_LEVEL`, and
the render/review timeout and resource-limit settings documented in the service
environment examples. `SUPABASE_URL` is required; the JWT issuer and JWKS URL
are derived from it unless explicitly overridden.

Do not configure an external `REDIS_URL` for this profile. The embedded Redis
binds only to loopback, uses append-only persistence, and is shared by the API
and both Celery workers.

The complete production checklist is in
[`docs/DEPLOYMENT.md`](../../docs/DEPLOYMENT.md).
