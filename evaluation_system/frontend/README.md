# RagBot Evaluation Frontend

The frontend is a Vite SPA. It calls the relative
`/api/v1/evaluation` namespace, so the deployed browser does not need an Eval
API hostname or cross-origin configuration.

## Local development

Install locked dependencies and start Vite from this directory:

```bash
npm ci
npm run dev
```

The development proxy defaults to `http://127.0.0.1:8090`. Set
`EVAL_API_DEV_PROXY` in a frontend-local environment file to use another Eval
API address.

## Build and container

```bash
npm run build
docker build -t ragbot-eval-frontend:local .
```

The container's final layer contains Nginx and `dist/` only. Nginx serves the
SPA, falls back to `index.html`, and proxies `/api/v1/evaluation/` to the
`eval-api` Compose service. The proxy is configured for unbuffered SSE.
