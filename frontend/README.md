# Manim Studio frontend

The frontend is a Vite + React application. It talks only to Backend; AI Core is never called from the browser.

Production deploys this directory as a standalone Vercel project. Configure
`VITE_API_BASE_URL=https://<protected-space>.hf.space/v1` and
`VITE_WS_BASE_URL=https://<protected-space>.hf.space/v1`; the WebSocket helper
converts the latter to `wss://`. Set `VITE_AUTH_MODE=jwt` and the public
Supabase variables in Vercel Production Environment Variables. GitHub Actions
uses `vercel build --prod` and uploads only `.vercel/output`.

## Run with Supabase JWT authentication

Copy `.env.example` to `.env`, keep `VITE_AUTH_MODE=jwt`, and set the public
Supabase URL plus `VITE_SUPABASE_PUBLISHABLE_KEY`. Production CI requires the
modern `sb_publishable_` format; the legacy anon-key variable remains a local
compatibility fallback. Then run:

```bash
npm ci
npm run dev
```

Never put `SUPABASE_SECRET_KEY` or a legacy service-role key in a `VITE_*`
variable. HTTP uses an Authorization bearer; WebSocket auth uses the
`Sec-WebSocket-Protocol` header so the token is not placed in a URL.

## Standalone local development

When Backend uses `AUTH_MODE=off`, set this frontend variable:

```dotenv
VITE_AUTH_MODE=off
```

The app then bypasses the login route, omits Bearer tokens, and opens the project WebSocket without a token. Blank Supabase browser values are safe in this mode. Do not use auth-off mode in production.

## Verification

```bash
npm test
npm run lint
npm run build
```
