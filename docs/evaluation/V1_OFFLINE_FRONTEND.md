# RagBot Evaluation V1 offline frontend deployment

## Runtime guarantee

The normal integrated deployment needs only:

1. the transferred contents of `evaluation_system/frontend/dist`;
2. the existing RagBot FastAPI process, which serves that build at `/evaluation`;
3. the same-origin `/api/v1/evaluation` control-plane path.

It does not need npm, Node.js, an npm registry, a CDN, Google Fonts, an icon server, telemetry, analytics, public images, public JavaScript, or public CSS at runtime.

Vazirmatn WOFF2 files and the OFL license are carried inside `dist/fonts`. Phosphor icons, React, TanStack Query, and TanStack Table are compiled into local JavaScript. Vite emits local CSS and JavaScript assets. The default API path is relative and same-origin.

## Connected build environment

Use the committed lockfile:

```bash
cd /root/projects/faq/evaluation_system/frontend
npm ci
VITE_EVALUATION_API_BASE=/api/v1/evaluation npm run build
npm run audit:offline
tar -C dist -czf ragbot-evaluation-ui-v1.tgz .
```

`npm ci` is the only step that may require package-registry connectivity. The archive contains the complete runtime artifact.

## Transfer and serve in an isolated environment

Copy `ragbot-evaluation-ui-v1.tgz` through the organization's approved artifact-transfer process, then extract it into a dedicated static root:

```bash
mkdir -p /opt/ragbot-evaluation-ui
tar -xzf ragbot-evaluation-ui-v1.tgz -C /opt/ragbot-evaluation-ui
```

For a controlled validation host with Python already installed:

```bash
python3 -m http.server 4173 --bind 127.0.0.1 --directory /opt/ragbot-evaluation-ui
```

For production, configure the internal reverse proxy or static server to:

- serve `/opt/ragbot-evaluation-ui/index.html` and its local `/assets` and `/fonts` paths;
- proxy `/api/v1/evaluation` to the internal evaluation API;
- preserve the `Last-Event-ID` request header;
- disable response buffering for `/api/v1/evaluation/runs/*/events`;
- allow long-lived `text/event-stream` responses;
- use internal TLS;
- add a CSP whose `default-src`, `script-src`, `style-src`, `font-src`, and `connect-src` are limited to the deployment's own approved internal origins.

The app uses query parameters rather than client-side route paths, so a general SPA fallback is not required. The static root must be deployed at the origin root when using the bundled absolute `/fonts` paths.

## Separate internal API origin

Same-origin deployment is preferred. If the evaluation API must use a separate internal origin, compile that approved origin in the connected environment:

```bash
VITE_EVALUATION_API_BASE=https://evaluation-api.internal.example npm run build
```

The backend must then list the exact frontend origin in its CORS allowlist. Never set a public API host. Never place credentials in `VITE_*` variables because Vite variables are compiled into public assets.

## Automated offline audit

Run:

```bash
cd /root/projects/faq/evaluation_system/frontend
npm run build
npm run audit:offline
```

The audit scans frontend source, public assets, Vite configuration, and built HTML/CSS/JavaScript/SVG/JSON for:

- `http://` and `https://` references;
- cdnjs, jsDelivr, unpkg, Google API/static/font hosts;
- external HTML asset attributes;
- external CSS `url(...)` assets;
- missing local HTML and CSS assets.

It explicitly classifies these non-request library literals:

- W3C DOM/SVG/MathML/XML namespace identifiers embedded by React and the local icon library;
- React's production error-documentation string;
- the loopback-only Vite development proxy.

Those literals do not create browser requests. Every actual script, style, font, and icon asset resolves locally. Acceptance output is:

```text
Offline frontend audit passed: external runtime asset requests = 0
```

## Operational checks after transfer

- Open the static page with public network access blocked.
- Confirm local CSS, JavaScript, and both WOFF2 font files return success.
- Sign in with an existing RagBot username/password and confirm only the approved internal evaluation API receives requests.
- Start or reopen a non-production validation run and confirm the SSE request remains connected.
- Reload the page, sign in again under the current process-local RagBot authentication semantics, and confirm the run can still be reopened.
- Confirm browser developer tools show no public host requests.

The current implementation was built and source/dist-audited locally. A real-browser network smoke test remains a validation-environment gate because no Playwright or Chromium binary was installed in the current workspace.
