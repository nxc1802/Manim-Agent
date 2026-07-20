# Manim Studio frontend

The frontend is a Vite + React application. It talks only to Backend; AI Core is never called from the browser.

## Run with Supabase JWT authentication

Copy `.env.example` to `.env`, keep `VITE_AUTH_MODE=jwt`, and set the public Supabase URL and publishable/anon key. Then run:

```bash
npm install
npm run dev
```

Never put `SUPABASE_SERVICE_ROLE_KEY` in a `VITE_*` variable.

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
