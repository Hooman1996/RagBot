# Offline frontend audit

Audit date: 2026-08-17

## Result

The dashboard had four public runtime resource references. It now has zero.
The primary outage cause was the knowledge-base page's unpinned Tailwind browser
script: almost all of that page's layout, spacing, colors, modal visibility, and
responsive behavior depended on `https://cdn.tailwindcss.com`. When it could not
load, the utility class names had no CSS definitions and the page rendered as
mostly unstyled HTML.

There were three additional problems:

- the analytics page requested Chart.js 4.4.4 from jsDelivr even though a local
  Chart.js 4.5.1 bundle was loaded later;
- all main UI pages imported Inter and JetBrains Mono from Google Fonts;
- the knowledge-base stylesheet imported Vazirmatn from a jsDelivr URL whose
  `v33.0.0` tag does not exist and returns HTTP 404 even with internet access.

## Entry points and first-party inventory

| Entry point | Template | Styles | Scripts | Main features |
| --- | --- | --- | --- | --- |
| `GET /` | `templates/login.html` | `base.css`, `login.css` | `api.js`, inline login/particles/i18n logic | Login, language and password toggles |
| `GET /app` | `templates/index.html` | `base.css`, `app.css` | `i18n.js`, `api.js`, `sidebar.js`, `categoryFilter.js`, `chat.js`, `app.js`, inline batch logic | Chat, datasource filtering, sessions, feedback, upload, mass answer |
| `GET /analytics` | `templates/analytics.html` | `base.css`, `app.css`, `analytics.css` | Chart.js, `analytics.js`, inline theme logic | KPIs, seven charts, heatmap, refresh/range controls |
| `GET /knowledge-base/` | `templates/kb_manager.html` | compiled Tailwind, Vazirmatn, `kb_manager.css` | `kb_manager.js` | Document/chunk table, search, create/edit/delete, history/revert, modals/toast |
| `GET /api/sessions/{id}/download` | Python-generated HTML in `main.py` | inline system-font CSS | none | Downloaded chat transcript; no network resource |

Other static files are `static/script.js`, `static/style.css`,
`static/js/dashboard.js`. They are legacy/unreferenced by the four mounted
templates, but were included in the source and network audit. There are no
project images, image files, SVG sprites, icon-font libraries, workers, WASM
modules, external modules, jQuery, Bootstrap, DataTables, Select2, SweetAlert,
Font Awesome, Axios, or frontend WebSocket/EventSource dependencies. Icons in
the current pages are text/emoji or CSS shapes.

The repository also contains ignored standalone Qdrant UI source/build trees
(`qdrant-web-ui-master`, `static_qdrant`). `main.py` does not mount or reference
them; their npm registry metadata is development/build metadata, not RagBot
dashboard browser runtime traffic.

## External reference classification before the change

| Exact reference | Classification | Used for | Failure effect | Criticality |
| --- | --- | --- | --- | --- |
| `https://cdn.tailwindcss.com` (redirected to 3.4.17 during audit) | Frontend runtime dependency | Knowledge-base utility CSS compiler | Most knowledge-base layout and controls lose styling; hidden/flex/modal states become incorrect | Critical |
| `https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js` | Frontend runtime dependency, redundant | Analytics charts | Public request fails; local 4.5.1 subsequently supplied `Chart`, so charts can still initialize | Low/redundant |
| `https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap` | Frontend runtime dependency | Main Latin/monospace typography | Browser falls back to system fonts; layout metrics can shift | Medium |
| `https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.0.0/Vazirmatn-font-face.css` | Frontend runtime dependency; invalid upstream tag | Knowledge-base Persian typography | Always 404; browser falls back to sans-serif | Medium |

Public URLs found in Markdown, licenses, package locks, source comments, Chart.js
license banners, and ordinary anchors are documentation, attribution,
development-only sources, or harmless hyperlinks. Backend-only service defaults
such as vLLM/Qdrant localhost URLs are not browser dependencies.

Before count: **4 source-level external runtime references**. After count:
**0**. The Google and Vazirmatn stylesheets would in turn have requested public
font files; their complete selected artifact trees are now local.

## Local third-party inventory and feature mapping

| Dependency | Preserved/pinned artifact | Local purpose | Local root |
| --- | --- | --- | --- |
| Tailwind CSS | 3.4.17 | Precompiled knowledge-base utilities; no browser compiler | `static/vendor/tailwind/3.4.17/` |
| Chart.js | 4.5.1 | Analytics canvases | `static/vendor/chart.js/4.5.1/` |
| Inter | Google Fonts endpoint revision v20, weights 300-800 | Main UI font | `static/vendor/google-fonts/` |
| JetBrains Mono | Google Fonts endpoint revision v24, weights 400-500 | Monospace UI font | `static/vendor/google-fonts/` |
| Vazirmatn | 33.003 | Persian/Arabic knowledge-base font, weights 100-900 | `static/vendor/vazirmatn/33.003/` |

Chart.js 4.5.1 was already the effective final browser version: the local bundle
loaded after the redundant 4.4.4 CDN tag and overwrote `window.Chart`. Tailwind
3.4.17 was identified from the CDN redirect and compiled on the build machine.
Vazirmatn 33.003 is the published compatible v33 release because the configured
33.0.0 artifact cannot be obtained. Exact files and hashes are in
`static/vendor/VENDOR_MANIFEST.json` and
`docs/frontend/OFFLINE_FRONTEND_DEPENDENCIES.md`.

## JavaScript network audit

All literal browser requests are same-origin paths:

- `/api/health`, `/api/login`, `/api/initialize`, `/api/documents`, `/api/query`;
- `/api/ocr/*`, `/api/sessions/*`, `/api/queries/*`, `/api/analytics`;
- `/api/mass-answer` and its server-returned status/result paths;
- `/knowledge-base/api/*`.

The variables `job.status_url` and `progress.result_url` are generated by
`main.py` as `/api/mass-answer/jobs/{id}` paths. The knowledge-base `endpoint`
variable is constructed from `/knowledge-base/api/chunks/{id}`. No public
`fetch`, Axios, XMLHttpRequest, dynamic import, worker, WebSocket, or EventSource
target exists.

## CSS and nested asset audit

- `base.css` no longer imports Google Fonts; templates load local `fonts.css`.
- `kb_manager.css` no longer imports jsDelivr; its template loads local
  `vazirmatn.css`.
- Google Fonts CSS was rewritten to local WOFF2 filenames and all 13 unique
  selected subset files are present.
- Vazirmatn CSS retains its original relative tree and all nine WOFF2 weights.
- Compiled Tailwind contains only embedded `data:` assets and local CSS.
- No external `@import` or `url(...)` remains.

## Static serving audit

Before, both `main.py` and `kb_manager.py` used the relative string
`"templates"`, and `main.py` mounted relative `"static"`. Starting Uvicorn from
another directory could fail template lookup or static initialization.

`frontend_paths.py` now resolves both directories from its own source file.
`main.py` mounts `STATIC_DIR` at `/static` with route name `static`; both Jinja
instances use `TEMPLATE_DIR`. All template assets use
`url_for('static', path=...)`. Importing `main` from `/tmp` verified the resolved
paths and route name. Relative font URLs remain inside their vendor stylesheet
directories. Python/Starlette reports `text/css`, a JavaScript MIME type, and
`font/woff2`; all tested resources returned 200.

For a path-prefix deployment, configure the ASGI `root_path` and forwarded host,
scheme, and prefix consistently. For the current root deployment, the proxy must
forward `/static/`, `/knowledge-base/`, and `/api/` to the same application and
must not rewrite browser API calls to server-side `localhost`.

## CSP, permissions, and browser tooling

No active CSP middleware, template meta CSP, or repository-owned reverse-proxy
configuration was found. `new_architecture/app/core/security.py` contains an
unused helper returning `default-src 'self'`; applying it as written would block
the templates' existing inline scripts/styles. Do not deploy it without first
adding nonces/hashes or moving inline code. A future tested policy should begin
with `default-src 'self'; connect-src 'self'; font-src 'self'; img-src 'self'
data:` and explicitly account for current inline content.

All frontend files are readable and none are world-writable. The service user is
not declared in this repository, so its exact identity is a DevOps deployment
fact. Recommended modes are directories `0755`, files `0644`, owned by the
deployment owner/group.

No Chromium, Chrome, Playwright, or browser executable was installed. Rendered
ASGI/static verification was completed; console/network and interaction checks
must follow the clean-cache manual procedure in the deployment guide.
