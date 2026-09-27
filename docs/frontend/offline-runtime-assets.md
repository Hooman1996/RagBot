# Main chatbot browser asset inventory

Scope: `/`, `/app`, `/analytics`, `/knowledge-base/`, and `/access-denied`.
The HTML for every page is `no-store`. First-party CSS, JS, and the SVG sprite use
`/_v/<SHA-256>/<path>` URLs with SRI on CSS and JS. A stale fingerprint returns
404; direct legacy static URLs are `no-store`. Vendor CSS and JS are pinned by
versioned paths, `VENDOR_MANIFEST.json` hashes, and SRI. Vendor font URLs are
relative to those local CSS files. A deploy should publish static files before
switching HTML to the new revision and retain old releases while in-flight pages
finish loading. A previously cached page from before this change may still use
its old unversioned links until it is replaced.

| Page | First-party files | Local vendor files | Icons |
| --- | --- | --- | --- |
| Login | `css/base.css`, `css/login.css`, `js/web_auth.js`, `js/api.js` | `vendor/google-fonts/fonts.css` → local Inter and JetBrains Mono WOFF2 | Inline SVG in `login.html` |
| Chat `/app` | `css/base.css`, `css/app.css`, `css/web_controls.css`, `js/web_auth.js`, `js/i18n.js`, `js/api.js`, `js/sidebar.js`, `js/categoryFilter.js`, `js/chat.js`, `js/app.js` | local Google fonts CSS/WOFF2 | `icons.svg` for navigation, theme, logout; existing in-page controls retain their current glyphs |
| Analytics | `css/base.css`, `css/app.css`, `css/analytics.css`, `css/web_controls.css`, `js/web_auth.js`, `js/analytics.js` | local Google fonts CSS/WOFF2 and `vendor/chart.js/4.5.1/chart.umd.js` | `icons.svg` for navigation, theme, refresh, five KPIs, eight chart headings, logout |
| Knowledge base | `css/kb_manager.css`, `css/web_controls.css`, `js/web_auth.js`, `js/kb_manager.js` | `vendor/tailwind/3.4.17/tailwind.min.css`, `vendor/vazirmatn/33.003/vazirmatn.css` → local Vazirmatn WOFF2 | `icons.svg` for back and logout |
| Access denied | `css/base.css`, `css/web_controls.css`, `js/web_auth.js` | none | `icons.svg` for logout |

All of these assets are served by FastAPI `/static`; no browser module import,
worker, image download, or remote icon/font/chart service appears in the active
page source. CSS `url()` dependencies are checked by `tests/test_offline_frontend.py`.
The chat, analytics, and knowledge-base scripts call same-origin `/api/*` and
`/knowledge-base/api/*` endpoints. User-facing links such as page navigation and
login's `href="#"` reset-password placeholder are links, not runtime assets.
The audit deliberately permits ordinary external `<a href>` links while rejecting
external runtime resources, forms, CSS imports/URLs, and script network targets.

## Local review on port 7000

1. Start the development app from this branch with the project's existing local
   environment: `uvicorn main:app --host 127.0.0.1 --port 7000`.
2. In a browser, block all hosts except `127.0.0.1` and `localhost`. Open `/`;
   sign in with local test accounts for `admin`, `analytics_viewer`, `user`, and
   `knowledge_editor` roles. Do not use production credentials.
3. Visit `/app`, `/analytics`, `/knowledge-base/`, and `/access-denied` as the
   appropriate roles. Check dark/light, English/Persian where offered, desktop
   (~1280px), medium (~768px), and narrow (~390px). Inspect navigation,
   logout, theme, KPI, chart-heading, and KB back icons and keyboard focus.
4. On analytics, select 7, 14, and 30 days. Check populated and empty responses,
   including heatmap and all five KPI cards. Inspect Network for any request to a
   nonlocal host or failing `/static/` asset, and Console for errors. Authorized
   roles should render analytics; denied roles should receive 403.
