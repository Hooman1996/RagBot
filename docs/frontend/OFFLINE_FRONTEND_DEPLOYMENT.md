# Offline frontend deployment

## What changed and why

The knowledge-base dashboard previously generated its CSS in the browser by
downloading Tailwind from a public CDN. On an offline server, that request failed
and the page's utility classes had no definitions. Public Chart.js, Google Fonts,
and an invalid Vazirmatn CDN import added more failed traffic. Those resources
are now pinned under `static/vendor/`, Tailwind is precompiled, and templates use
the FastAPI `static` route.

`frontend_paths.py` makes template and static paths relative to the application
source rather than the startup shell's current directory. No database, RAG,
model, vLLM, TEI, or environment configuration changed.

## Package contents

The deployment artifact must include at least:

```text
frontend_paths.py
templates/
static/
  css/
  js/
  vendor/
    VENDOR_MANIFEST.json
    chart.js/4.5.1/
    google-fonts/
    tailwind/3.4.17/
    vazirmatn/33.003/
```

Do not copy only the top-level CSS files: the WOFF2 trees and license notices are
required. Production startup requires no npm, yarn, pnpm, pip frontend package,
curl, wget, or internet access.

## Pre-deployment validation

From `/root/projects/faq`:

```bash
python3 scripts/audit_offline_frontend.py
/root/miniconda3/envs/faq/bin/python3.12 -m unittest -v tests.test_offline_frontend
```

Expected audit result:

```text
Offline frontend audit: PASS
External runtime dependencies: 0
```

The test suite renders all four Jinja templates, checks source classification,
recursively resolves CSS/font assets, validates vendor hashes, checks safe paths
and permissions, and requests template-linked CSS/JS plus every WOFF2 file from
Starlette StaticFiles. The verified result on 2026-08-17 was 8/8 tests passing,
17 distinct template-linked static resources returning 200, and zero static
404s.

## Local application test

Use the normal project interpreter and configuration:

```bash
cd /root/projects/faq
/root/miniconda3/envs/faq/bin/python3.12 -m uvicorn main:app --host 127.0.0.1 --port 8000
```

This starts the full application and therefore still requires its normal
internal PostgreSQL, Qdrant, MinIO, vLLM, and TEI services. It does not require
public internet. Do not run this command against production as part of an
automated deployment; use the site's existing service manager.

## Clean-cache offline browser test

No headless browser was installed in the audit environment, so perform this
final staging check before promotion:

1. Open a private/incognito browser window with DevTools Network and Console open.
2. Enable “Disable cache”, clear site data, then block outbound internet for the
   temporary test client/network namespace (do not change the host firewall
   permanently).
3. Visit `/`, `/app`, `/analytics`, and `/knowledge-base/`.
4. Filter Network by `scheme:http`/`scheme:https` and confirm every automatic
   request uses the RagBot origin; user-clicked documentation links are exempt.
5. Confirm all CSS, JavaScript, WOFF2 fonts, and icons return 200; there must be
   no required 404, DNS failure, CSP failure, or JavaScript exception.
6. Verify login controls, theme/language toggles, sidebar/navigation, datasource
   filtering, chat form and upload UI, session menus, feedback/comment controls,
   analytics range/refresh and all charts, knowledge-base search/table, load
   more, add/edit/delete, history/revert, modals, and toast behavior.
7. Reload while still offline and with cache disabled. Confirm the layout and
   typography remain intact.

Acceptance values are:

```text
External network requests required for dashboard: 0
Required static asset 404s: 0
Required JavaScript errors: 0
```

## Reverse proxy

The proxy must send these paths to the same FastAPI application:

- `/static/`
- `/api/`
- `/knowledge-base/`
- `/`, `/app`, `/analytics`

Preserve the original host and scheme using the proxy's standard forwarded
headers and configure the ASGI server to trust only the proxy. For a deployment
under a URL prefix, set the matching ASGI `root_path`; `url_for('static', ...)`
will then generate the correct prefix. No browser-side code should be rewritten
to a server-side `localhost` URL. Same-origin API paths must remain intact.

## Permissions

The repository does not identify the production service user. Determine it from
the systemd/Supervisor/container definition, then use deployment ownership and
read-only runtime permissions such as:

```text
directories: 0755
files:       0644
owner/group: deployment owner and the service-readable group
```

Do not make frontend files world-writable. Ensure the service user can traverse
the repository parent directories and read `templates/`, `static/`, and every
vendor/font subdirectory.

## Content Security Policy

There is no active CSP in the mounted application. Do not enable the unused
`default-src 'self'` helper unchanged: the current templates contain inline
scripts and styles. First move inline code to local files or deploy tested
nonces/hashes. A target local-only policy can use `default-src 'self'`,
`connect-src 'self'`, `font-src 'self'`, and `img-src 'self' data:`, with the
minimum temporary inline allowances required during migration. Validate every
page for CSP console errors before production rollout.

## Updating a dependency later

1. Pin the exact desired version on an internet-connected build machine.
2. Review release notes and license; do not change major versions silently.
3. Download the complete dependency tree, including fonts/assets/workers/WASM.
4. For Tailwind, rebuild `tailwind.min.css` from `input.css` while scanning
   `kb_manager.html` and `kb_manager.js`; never add the browser CDN compiler.
5. Update template paths, retained licenses, dependency documentation, and every
   SHA256 in `VENDOR_MANIFEST.json`.
6. Run the audit/tests and the clean-cache offline browser procedure.
7. Compare appearance and interactions before deployment.

For the currently pinned standalone Tailwind build tool, the build-machine
command is:

```bash
./tailwindcss-v3.4.17 \
  -i static/vendor/tailwind/3.4.17/input.css \
  -o static/vendor/tailwind/3.4.17/tailwind.min.css \
  --content templates/kb_manager.html,static/js/kb_manager.js \
  --minify
```

Do not ship or invoke that build binary on the production server.

## Rollout actions

An application/service restart or rolling reload is required after deploying
the changed Python/templates/static artifact so workers pick up the absolute
path code and templates. Do not restart automatically from this repository.
Invalidate any reverse-proxy/browser static cache if it keys old template asset
paths. No `.env` change, database migration, model change, or production
infrastructure mutation is required. There are no unresolved public runtime
dependencies.
