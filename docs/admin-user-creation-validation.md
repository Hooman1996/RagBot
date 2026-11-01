# Admin user creation: local validation

Validated on 2026-10-28. Starting branch: `main`; starting HEAD:
`fc2f6a1dc85be71f782868f18833a895e502226a`.
The local worktree was inspected without pulling, resetting, switching commits,
committing, pushing, deploying, or restarting application services. Pre-existing
untracked benchmarks, documentation, and `test.json` were left untouched.

## Implementation

- Page: `GET /admin/users`. Creation: `POST /api/admin/users`.
- Permission: `users_manage`, granted only to `admin` and explicitly registered
  for both routes. Existing signed-cookie identity, CSRF, origin checks, and
  current database role remain the authorization mechanism. Unknown roles/routes
  remain denied. Creation does not set session cookies or replace the acting admin.
- Shared, non-interactive validation, hashing, duplicate mapping, and INSERT live
  in `web_user_accounts.py`; the CLI retains its commands, prompts, target checks,
  preview/apply workflow, and transaction ownership. Unicode confirmation now
  compares UTF-8 bytes exactly. No normalization or password truncation occurs.
- The API uses the configured `DatabaseManager.get_connection`, not CLI env-file
  selection. Its bounded worker hashes before acquiring the write connection and
  uses `wait_for_completion_on_cancel=True`, parameterized SQL, commit/rollback,
  and connection cleanup. Unique violations are mapped before generic safe errors.
- Creation accepts only the six documented strings. The response has an explicit
  account-field allowlist. Validation errors contain fixed field/error codes;
  creation request/response bodies are excluded from HTTP logging. Early browser
  authentication/CSRF/origin responses now also carry `Cache-Control: no-store`.
- The dashboard reuses local fonts, icons, colors, focus controls, saved theme and
  language, and fingerprinted assets with integrity attributes. The Users partial
  is permission gated; Knowledge Base retains its header. Knowledge coverage
  remains the final navigation link, preserving its existing regression contract.
- No schema change or migration is necessary under the active DatabaseManager/CLI
  users-table contract. The database generates the integer ID; shared provisioning
  supplies UUID, bcrypt hash, active/unverified flags, empty settings and UTC
  timestamps, leaving last login and optional profile fields unset. The legacy
  initial Alembic migration was not used. Existing DB credentials need their normal
  user INSERT and ID-sequence access. Release Python/templates/static assets
  together using the normal release process; nothing was deployed here.

## Changed files

Backend and CLI:
`main.py`, `web_permissions.py`, `web_auth.py`, `web_user_accounts.py`,
`scripts/manage_web_users.py`, `utils/http_logging_middleware.py`.

UI and assets:
`templates/admin_users.html`, `templates/_users_nav_link.html`,
`templates/index.html`, `templates/analytics.html`,
`templates/knowledge_coverage.html`, `templates/kb_manager.html`,
`static/css/admin_users.css`, `static/js/admin_users.js`, `static/js/i18n.js`,
`versioned_assets.py`.

Verification and documentation:
`tests/test_admin_users.py`, `tests/admin_users.frontend.test.cjs`,
`tests/test_manage_web_users.py`, `tests/test_web_permissions.py`,
`tests/test_offline_frontend.py`, `scripts/run_offline_tests.sh`,
`docs/manage-web-users.md`, and this report.

## Commands and actual results

Run from `/root/projects/faq`, using conda environment `faq`:

```sh
timeout 120 conda run --no-capture-output -n faq python -m pytest -p tests.offline_guard tests/test_admin_users.py tests/test_web_auth.py tests/test_web_permissions.py tests/test_manage_web_users.py tests/test_offline_frontend.py tests/test_coverage_check.py -q
```

Result: **258 passed**, 48 warnings, 33.30 seconds.
Log: `/tmp/faq-admin-focused-final.log`.

```sh
conda run --no-capture-output -n faq bash scripts/run_offline_tests.sh
```

Result: **935 passed**, 26 deselected, 295 subtests passed; all four Node harnesses
passed; offline frontend audit reported zero external runtime dependencies;
tracked-secret check reported zero matches. Log: `/tmp/faq-admin-offline-final.log`.
The runner includes the new `node tests/admin_users.frontend.test.cjs` harness;
that harness was also run separately and passed.

```sh
git diff --check
node --check static/js/admin_users.js
python -m py_compile web_user_accounts.py tests/test_admin_users.py scripts/manage_web_users.py
```

All passed. A sandboxed TestClient attempt stalled in its cross-thread event loop
and was stopped. Final Python checks ran outside that sandbox with
`tests.offline_guard` still blocking network/PostgreSQL connections. Initial
fixture failures were corrected. The first full offline run identified four
existing navigation-order regressions; placing Users before Knowledge coverage
resolved them without changing or weakening those tests.

## Browser verification

Available local Chromium and Playwright were used against a temporary loopback
preview of the real routes/templates/assets. The preview replaced application
startup and all accounts/connections with in-memory synthetic dependencies and
blocked `psycopg2.connect` before importing the app. No configured live database
was contacted and no demonstration accounts were written there.

```sh
conda run --no-capture-output -n faq python /tmp/faq-admin-browser-server.py
timeout 120 node /tmp/faq-admin-users-browser.cjs
```

Result: **PASS**. Verified at 1440×1000 and 390×844: English/Persian,
LTR/RTL inputs, dark/light themes, required/mismatched-field feedback, six
server-generated role choices and ordinary-user default, disabled loading button,
real 201/409 submissions, password clearing, preserved admin identity, navigation
from Chat/Analytics/Knowledge Base/Knowledge coverage, and non-admin menu hiding
plus page/API denial. Mobile screenshots wait for responsive transitions to
settle. The temporary preview was stopped after verification.

Final browser output: `/tmp/faq-admin-browser-final.log`.
Screenshots: `/tmp/faq-admin-users-browser/desktop-loading.png`,
`desktop-persian-light.png`, `mobile-persian-light.png`, `mobile-english-dark.png`.
The temporary preview/harness and screenshots are local validation artifacts;
the reproducible frontend harness lives under `tests/`.

Live PostgreSQL, production connectivity, deployment, and real-account login
were deliberately not exercised. Stored bcrypt verification uses the actual
`AuthenticationService` with fake SQL connections. Retrieval/answer-quality
benchmarks were unnecessary because model behavior and retrieval were unchanged.

## Manual acceptance

Use an isolated test database or an approved staging account:

1. As admin, open Users, confirm `user` is selected, fill all six fields and submit.
   Confirm loading state, safe success summary, cleared passwords, and that the
   acting account remains the admin. Check duplicate and mismatched-password
   feedback. Switch FA/EN and theme; check the narrow layout. A separately
   created account should log in with its assigned role.
2. As a non-admin, verify Users is absent. Direct `GET /admin/users` and an
   authenticated `POST /api/admin/users` must return 403. Without a session,
   the page redirects to login and the API returns 401.
