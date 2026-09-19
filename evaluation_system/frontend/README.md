# RagBot Evaluation Frontend

This independent Vite/React project builds a static Evaluation UI. Production
uses Nginx for both static serving and same-origin proxying:

```text
Browser -> /api/v1/evaluation/* -> Nginx -> Eval Backend API
```

The frontend has no direct RagBot connection and no runtime Node server.

## Development

Run from this directory, which is the future repository root:

```bash
npm ci
npm run dev
```

Vite proxies `/api/v1/evaluation` to `http://127.0.0.1:8090` by default. Copy
`.env.example` to an untracked local environment file to set a different
`EVAL_API_DEV_PROXY`. This setting is development-only; production browser
traffic remains same-origin through Nginx and needs no API hostname baked into
the UI.

## Validation

```bash
npm run test
npm run build
npm run audit:offline
```

These checks do not require a running backend.

## Container and routing

```bash
docker build -t ragbot-eval-frontend:local .
```

The multi-stage build uses Node only to produce `dist/`. The final image is
Nginx plus the static UI and `nginx.conf`; it contains no source dependency on
the backend or RagBot. `NPM_REGISTRY_URL` is a configurable build argument and
defaults to the official npm registry.

Nginx serves hashed static assets with long-lived caching and enables gzip for
static text assets. It proxies `/api/v1/evaluation/` to the Eval API. Proxy
buffering, request buffering, caching, and gzip are disabled on that API/SSE
location so server-sent events remain unbuffered. The production platform must
provide DNS/network reachability from Nginx to the Eval API.
