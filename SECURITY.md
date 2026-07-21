# Security policy and deployment boundary

## Supported profile

The supported initial production profile is a protected/private, single-tenant Hugging Face Docker Space operated by a trusted team. Generated and user-edited Manim Python executes inside the same container as application processes. AST checks, a minimal subprocess environment, non-root execution and resource limits are defense in depth; they are **not a complete sandbox**.

Do not expose this profile as an anonymous or hostile multi-tenant code-execution service. That requires an isolated ephemeral render job with a separate UID/VM boundary, no database/provider secrets, disabled or policy-controlled network, a one-time claim token, and presigned artifact upload.

## Controls in this repository

- Supabase JWT ES256/RS256 verification uses issuer/audience checks and JWKS caching; HS256 requires an explicit legacy secret.
- Browser JWTs travel in `Authorization` for HTTP and the WebSocket subprotocol header for sockets, not in URLs.
- HTTP responses deny framing and MIME sniffing, restrict referrers/browser permissions, and enable HSTS outside development.
- Application tables revoke `anon`/`authenticated` grants; Backend-only `service_role` access is explicit, with forced RLS as defense in depth.
- Supabase secret/service-role credentials never belong in Frontend or AI Core.
- Supervisor strips all application secrets from Redis, provider keys from Backend, and database/JWT secrets from both workers before process start.
- Workers are non-root, queues use late acknowledgement, and render tasks have hard/soft time and resource limits.
- Generated-code subprocesses receive a sanitized environment; sensitive paths, external URLs, reflection, unsafe imports and file-backed NumPy operations are rejected before execution.
- Production dependencies are exact, hash-locked and audited; CI builds and scans the root image before CD.

## Secret ownership

| Secret | Owner |
| --- | --- |
| `SUPABASE_SECRET_KEY` / legacy service-role key | Backend runtime only |
| `SUPABASE_JWT_SECRET` (legacy only) | Backend runtime only |
| `GOOGLE_API_KEY*` | AI/render runtime only |
| `INTERNAL_SERVICE_TOKEN` | Backend and workers in the same deployment |
| `HF_TOKEN`, Supabase access token/database password | GitHub production deployment only |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Public browser configuration; not a secret |

Never commit `.env` files. Never place a secret in `VITE_*`, Docker `ARG`, README, workflow logs, Redis key names, URL query strings or exception bodies.

## Reporting

Report suspected vulnerabilities privately to the repository owner/maintainers with affected revision, reproduction steps and impact. Do not include live credentials or personal data and do not open a public issue before a fix/rotation plan exists.
