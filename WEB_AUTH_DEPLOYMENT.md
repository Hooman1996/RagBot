# Browser authentication for local development and CI/CD deployment

## Route boundary

The web guard applies the explicit route-to-permission inventory in [WEB_ROLE_PERMISSIONS.md](WEB_ROLE_PERMISSIONS.md). Unclassified browser routes are denied by default. Authenticated users without the required permission get a 403 page or JSON response; unauthenticated API requests get 401 and protected pages redirect to login. State-changing web requests retain CSRF validation.

- Public: `/` (login page), `/api/login`, `/api/health`, `/static/*`, and FastAPI's generated `/docs`, `/redoc`, and `/openapi.json`.
- Separate contracts: `/api/mobile/*` and `/api/internal/evaluation/v1/*` do not use the browser cookie. The app does not impose web authentication on them. Confirm their network and gateway controls independently before production rollout.

Chat session IDs are checked against the authenticated user's ID from the signed cookie and the existing `chat_sessions.user_id` before reads, messages, writes, deletes, pinning, satisfaction, and downloads. Query feedback and comments use the owning chat session. Async mass-answer jobs have their existing schema; job status, result, and deletion require a signed access value bound to the authenticated user ID and job ID. The access value is returned in the job creation response and sent in the `X-Job-Access` header for polling, result download, and deletion. It is never placed in a URL. Existing jobs created before this change have no such URL and cannot be opened through the protected browser endpoints. No chatbot schema or table is added or altered.

## Signed session and CSRF

Login uses the existing password service and returns only `{success, landing_path, user: {id, username, display_name, role, permissions, landing_path}}`. `/api/auth/me` returns the same safe user fields. The role and active status come from the current database row, and permissions are calculated by the reviewed server policy on each request. The browser uses the landing path and permissions only to guide the UI; API checks are authoritative. The `ragbot_web_session` cookie is signed with HMAC-SHA-256 using `WEB_SESSION_SECRET`. Its payload contains only an integer user ID, issue and expiration times, and a random nonce. The session cookie is `HttpOnly`, `SameSite=Strict`, host-only, and path `/`; it is `Secure` in HTTPS mode. Signatures and expiry are verified on **every request**, followed by a read-only lookup of `users(id, username, full_name, role, is_active)` in the existing database. An inactive or missing user is denied.

A second cookie, `ragbot_web_csrf`, contains a token derived from the signed session nonce. The browser script sends it in `X-CSRF-Token` for same-origin mutating web requests. The server verifies both values and checks `Origin` when supplied. The token is not an identity claim. The default lifetime is **900 seconds (15 minutes)**, bounded in code to 5–60 minutes. There is no sliding renewal. Rotating `WEB_SESSION_SECRET` invalidates all cookies and outstanding mass-answer job access values signed with the previous secret, so all workers must share the same secret during normal operation.

`/api/auth/logout` clears both cookies in the current browser. **It cannot revoke a copied cookie server-side. A copied, otherwise valid cookie remains usable until its signed expiration, unless the user is deactivated or the shared signing secret is rotated.** Do not describe logout as global revocation. The login page does not initialize the document system; system initialization now requires the `system` grant. GET `/api/sessions` is read-only; when it is empty, the browser creates the usual initial chat through CSRF-protected POST.

## Ubuntu development server with VS Code Remote-SSH

The untracked `.env` on this server has the following variable names, with a generated strong secret kept private. The `env.example` placeholder is deliberately too short for startup; generate a real value with a secret manager or `openssl rand -hex 32`:

```text
WEB_ENVIRONMENT
WEB_COOKIE_MODE
WEB_PUBLIC_ORIGIN
WEB_SESSION_SECONDS
WEB_SESSION_SECRET
```

For this server the non-secret WEB settings are development, local-http, `http://localhost:7000`, and 900 seconds. Start the app on the Ubuntu server from the repository root:

```bash
/root/miniconda3/envs/faq/bin/python -m uvicorn main:app --host 127.0.0.1 --port 7000
```

Forward port `7000` in VS Code Remote-SSH and open **`http://localhost:7000`** in the local browser. Use `localhost` consistently; an origin of `http://127.0.0.1:7000` is different. Local HTTP mode starts only with `WEB_ENVIRONMENT=development` and an explicit localhost origin. The cookie omits `Secure` only in this development mode. `.env` is untracked and must remain uncommitted.

Run the focused and relevant tests:

```bash
/root/miniconda3/envs/faq/bin/python -m pytest -q tests/test_web_auth.py tests/test_web_permissions.py tests/test_kb_manager_database_config.py tests/test_kb_manager_chunk_create.py tests/test_mass_answer_jobs.py tests/test_mass_answer_regressions.py tests/test_internal_evaluation_api.py tests/test_mobile_history_content.py tests/test_offline_frontend.py
```

For a manual browser check, log in as two existing test users in separate profiles. Confirm `/api/auth/me` returns only safe fields, each sees only its own sessions, a cross-user session ID returns 404, a mutating API call without `X-CSRF-Token` returns 403, and logout returns the current browser to login. The automated tests cover signed expiration and the copied-cookie logout limit.

## Production CI/CD and gateway decisions

Supply the same strong `WEB_SESSION_SECRET` to every worker through the CI/CD secret manager; do not place it in the image, repository, or logs. Set `WEB_ENVIRONMENT=production`, `WEB_COOKIE_MODE=https`, `WEB_PUBLIC_ORIGIN=https://<exact-browser-origin>` (include a nonstandard port if used), and `WEB_SESSION_SECONDS=900` unless a shorter policy is chosen. The app refuses to start in HTTPS mode without an external HTTPS origin. The gateway must terminate HTTPS and forward `Cookie`, `Origin`, `X-CSRF-Token`, and `X-Job-Access` without logging their values. Verify that `Set-Cookie` reaches the browser with `Secure; HttpOnly; SameSite=Strict` on the session cookie and that the origin matches exactly. Keep `/api/mobile/*` and `/api/internal/evaluation/v1/*` behind their intended independent gateway/network controls.

If central logout or immediate revocation becomes required, choose shared server-side state (for example a gateway session store or a revocation registry) and define its availability, expiry cleanup, and secret rotation procedures. If the gateway later manages identity, it must authenticate each request, strip any client-supplied identity headers, and send authenticated identity only over a trusted hop with an explicit verification contract in the app. **Never trust a browser-supplied identity header merely because a gateway exists.** Neither feature is implemented in this step.

The live gateway behavior is not established from this repository. Verify HTTPS forwarding, origin behavior, cookie flags, and separate mobile/evaluation routing in a staging deployment before production rollout. No database migration is required.

## Credential and gateway gates before wider access

The seed script now requires a fresh password for each new account from a private
`RAGBOT_SEED_PASSWORD_<USERNAME>` secret-manager environment injection or a
terminal `getpass` prompt. It never prints generated credentials. The historical
source committed plaintext defaults for the seeded `admin`, `johndoe`,
`janesmith`, `moderator`, and `alicejohnson` accounts. Removing those literals
from working code does not erase Git history. Before wider access, an operator
must check whether these accounts exist, rotate each retained account to a new
unique password through the approved private account procedure, deactivate
unused accounts, revoke any copied sessions as required, and audit the change.
A safe sequence is: identify the account by username in a restricted operator
session; approve retain versus deactivate; generate a unique password in a
secret manager or private terminal; hash it with the application's bcrypt
policy; use a parameterized `UPDATE users SET password_hash = :new_hash,
updated_at = NOW() WHERE id = :approved_id` (or set `is_active = FALSE` for
an unused account) inside a transaction; verify exactly one row changed;
commit and test the retained account through the private login flow. Keep
plaintext out of SQL, shell arguments, tickets, logs, and the repository.
Password rotation alone does not revoke existing signed cookies; deactivation
immediately blocks them, while a coordinated signing-secret rotation invalidates
all browser sessions if urgent global revocation is required. This task does not
change any user row.

Expose `/api/login` broadly only after a gateway login throttle or another
shared, multi-worker control is configured and tested, with monitoring and an
incident response threshold. A per-process limiter is insufficient across
multiple workers. Production HTTPS, cookie forwarding, origin handling, and
independent mobile/evaluation gateway routing remain deployment gates.
