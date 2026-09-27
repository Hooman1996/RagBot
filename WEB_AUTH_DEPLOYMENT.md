# Browser authentication for local development and CI/CD deployment

## Route boundary

The web guard covers `/app`, `/analytics`, `/knowledge-base` and every `/knowledge-base/*` route. It also covers every `/api/*` route except the paths below. This includes documents, initialization, query, chat sessions and downloads, feedback, OCR, mass-answer and its jobs, analytics, and admission metrics. State-changing web requests require CSRF validation.

- Public: `/` (login page), `/api/login`, `/api/health`, `/static/*`, and FastAPI's generated `/docs`, `/redoc`, and `/openapi.json`.
- Separate contracts: `/api/mobile/*` and `/api/internal/evaluation/v1/*` do not use the browser cookie. The app does not impose web authentication on them. Confirm their network and gateway controls independently before production rollout.

Chat session IDs are checked against the authenticated user's ID from the signed cookie and the existing `chat_sessions.user_id` before reads, messages, writes, deletes, pinning, satisfaction, and downloads. Query feedback and comments use the owning chat session. Async mass-answer jobs have their existing schema; job status, result, and deletion require a signed access value bound to the authenticated user ID and job ID. The access value is returned in the job creation response and sent in the `X-Job-Access` header for polling, result download, and deletion. It is never placed in a URL. Existing jobs created before this change have no such URL and cannot be opened through the protected browser endpoints. No chatbot schema or table is added or altered.

## Signed session and CSRF

Login uses the existing password service and returns only `{success, user: {id, username, display_name, role}}`. The `ragbot_web_session` cookie is signed with HMAC-SHA-256 using `WEB_SESSION_SECRET`. Its payload contains only an integer user ID, issue and expiration times, and a random nonce. The session cookie is `HttpOnly`, `SameSite=Strict`, host-only, and path `/`; it is `Secure` in HTTPS mode. Signatures and expiry are verified on **every request**, followed by a read-only lookup of `users(id, username, full_name, role, is_active)` in the existing database. An inactive or missing user is denied.

A second cookie, `ragbot_web_csrf`, contains a token derived from the signed session nonce. The browser script sends it in `X-CSRF-Token` for same-origin mutating web requests. The server verifies both values and checks `Origin` when supplied. The token is not an identity claim. The default lifetime is **900 seconds (15 minutes)**, bounded in code to 5–60 minutes. There is no sliding renewal. Rotating `WEB_SESSION_SECRET` invalidates all cookies and outstanding mass-answer job access values signed with the previous secret, so all workers must share the same secret during normal operation.

`/api/auth/logout` clears both cookies in the current browser. **It cannot revoke a copied cookie server-side. A copied, otherwise valid cookie remains usable until its signed expiration, unless the user is deactivated or the shared signing secret is rotated.** Do not describe logout as global revocation. The login page does not initialize the document system; the existing initialization button remains an explicit authenticated action. GET `/api/sessions` is read-only; when it is empty, the browser creates the usual initial chat through CSRF-protected POST.

## Ubuntu development server with VS Code Remote-SSH

The untracked `.env` on this server has the following variable names, with a generated strong secret kept private. The `env.example` placeholder is deliberately too short for startup; generate a real value with a secret manager or `openssl rand -hex 32`:

```text
WEB_ENVIRONMENT
WEB_COOKIE_MODE
WEB_PUBLIC_ORIGIN
WEB_SESSION_SECONDS
WEB_SESSION_SECRET
```

For this server the non-secret WEB settings are development, local-http, `http://localhost:8765`, and 900 seconds. Start the app on the Ubuntu server from the repository root:

```bash
/root/miniconda3/envs/faq/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8765
```

Forward port `8765` in VS Code Remote-SSH and open **`http://localhost:8765`** in the local browser. Use `localhost` consistently; an origin of `http://127.0.0.1:8000` is different. Local HTTP mode starts only with `WEB_ENVIRONMENT=development` and an explicit localhost origin. The cookie omits `Secure` only in this development mode. `.env` is untracked and must remain uncommitted.

Run the focused and relevant tests:

```bash
/root/miniconda3/envs/faq/bin/python -m pytest -q tests/test_web_auth.py tests/test_kb_manager_database_config.py tests/test_kb_manager_chunk_create.py tests/test_mass_answer_jobs.py tests/test_mass_answer_regressions.py tests/test_internal_evaluation_api.py tests/test_mobile_history_content.py tests/test_offline_frontend.py
```

For a manual browser check, log in as two existing test users in separate profiles. Confirm `/api/auth/me` returns only safe fields, each sees only its own sessions, a cross-user session ID returns 404, a mutating API call without `X-CSRF-Token` returns 403, and logout returns the current browser to login. The automated tests cover signed expiration and the copied-cookie logout limit.

## Production CI/CD and gateway decisions

Supply the same strong `WEB_SESSION_SECRET` to every worker through the CI/CD secret manager; do not place it in the image, repository, or logs. Set `WEB_ENVIRONMENT=production`, `WEB_COOKIE_MODE=https`, `WEB_PUBLIC_ORIGIN=https://<exact-browser-origin>` (include a nonstandard port if used), and `WEB_SESSION_SECONDS=900` unless a shorter policy is chosen. The app refuses to start in HTTPS mode without an external HTTPS origin. The gateway must terminate HTTPS and forward `Cookie`, `Origin`, `X-CSRF-Token`, and `X-Job-Access` without logging their values. Verify that `Set-Cookie` reaches the browser with `Secure; HttpOnly; SameSite=Strict` on the session cookie and that the origin matches exactly. Keep `/api/mobile/*` and `/api/internal/evaluation/v1/*` behind their intended independent gateway/network controls.

If central logout or immediate revocation becomes required, choose shared server-side state (for example a gateway session store or a revocation registry) and define its availability, expiry cleanup, and secret rotation procedures. If the gateway later manages identity, it must authenticate each request, strip any client-supplied identity headers, and send authenticated identity only over a trusted hop with an explicit verification contract in the app. **Never trust a browser-supplied identity header merely because a gateway exists.** Neither feature is implemented in this step.

The live gateway behavior is not established from this repository. Verify HTTPS forwarding, origin behavior, cookie flags, and separate mobile/evaluation routing in a staging deployment before production rollout. No database migration is required.
