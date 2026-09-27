# Browser route and permission inventory (Step 2)

This is the reviewed initial policy for the existing web UI. `web_permissions.py` is
the only role-to-permission mapping. A change to that mapping requires a reviewed
code/config deployment; there is no live role editor. Role and active status are
read from `users` on every browser request. The cookie carries identity only.

| Permission | Browser routes and methods |
| --- | --- |
| `chat` | GET `/app`; POST `/api/query` |
| `sessions` | GET, POST `/api/sessions`; GET, DELETE `/api/sessions/{id}`; POST `/api/sessions/{id}/message`, `/satisfaction`; GET `/api/sessions/{id}/messages`; PATCH `/api/sessions/{id}/pin` |
| `feedback` | PATCH `/api/queries/{id}/feedback`, `/comment` |
| `downloads` | GET `/api/sessions/{id}/download` |
| `documents` | GET `/api/documents` |
| `ocr` | GET `/api/ocr/status`; POST `/api/ocr/extract` |
| `analytics` | GET `/analytics`, `/api/analytics` |
| `kb_page` | GET `/knowledge-base`, `/knowledge-base/` |
| `kb_read` | GET `/knowledge-base/api/documents`, `/knowledge-base/api/chunks/{document_id}`, `/knowledge-base/api/chunks/{chunk_id}/versions` |
| `kb_write` | POST `/knowledge-base/api/chunks/create`, `/knowledge-base/api/chunks/revert`; PUT `/knowledge-base/api/chunks/update`; DELETE `/knowledge-base/api/chunks/delete/{chunk_id}` |
| `batch` | POST `/api/mass-answer`; GET `/api/mass-answer/jobs/{job_id}`, `/result`; DELETE `/api/mass-answer/jobs/{job_id}` |
| `system` | POST `/api/initialize`; GET `/api/metrics/admission`; POST `/api/mass-answer/jobs/cleanup` |

Chat and session APIs retain the existing owner checks. Feedback and comments retain
query ownership checks. Batch job access also requires its existing user-bound
`X-Job-Access` value. Permissions alone never confer access to another user's data.

| Role | Effective permission identifiers | Landing path |
| --- | --- | --- |
| `admin` | `chat`, `sessions`, `feedback`, `downloads`, `documents`, `ocr`, `analytics`, `kb_page`, `kb_read`, `kb_write`, `batch`, `system` | `/app` |
| `user` | `chat`, `sessions`, `feedback`, `downloads`, `documents`, `ocr` | `/app` |
| `moderator` | same as `user`; no elevated access yet | `/app` |
| `analytics_viewer` | `analytics` | `/analytics` |
| `knowledge_editor` | `kb_page`, `kb_read`, `kb_write` | `/knowledge-base/` |
| unknown role | none | `/access-denied` |

A read-only `SELECT DISTINCT role` against the configured development database on
2026-09-27 returned `admin`, `moderator`, and `user`. No individual records or
passwords were retrieved or changed.

To grant batch access later, add `batch` to the desired role in `web_permissions.py`
and review/deploy that policy change. No database migration is needed.

Public exemptions are GET `/` (login), POST `/api/login`, GET `/api/health`,
`/static/*`, and FastAPI's generated `/docs`, `/redoc`, `/openapi.json`.
`/api/auth/me` and POST `/api/auth/logout` require a valid browser session but no
product permission. GET `/access-denied` is an authenticated informational landing
page for roles with no product permission. `/api/mobile/*` and
`/api/internal/evaluation/v1/*` keep their independent contracts; browser cookie
authentication and CSRF are not applied to them. All other browser routes,
including newly added or mistyped `/api/*` paths, are denied until classified.
Unauthenticated APIs return 401 and protected pages redirect to `/`; authenticated
requests without permission return 403 JSON or a 403 page.

## Role assignment procedure (dry run)

Use a restricted operator SQL session against the intended database. First verify
the selected account by ID through an approved private channel. Within a
transaction, run the parameterized form of this query and inspect the returned
ID and current role; **ROLLBACK** for this dry run:

```sql
BEGIN;
SELECT id, role, is_active FROM users WHERE id = :target_user_id FOR UPDATE;
UPDATE users SET role = :approved_role WHERE id = :target_user_id
  RETURNING id, role;
ROLLBACK;
```

After an approved change, repeat with `COMMIT` and audit the role change through
the operator's normal change process. This task does not assign any real roles.
