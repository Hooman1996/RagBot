# Browser role permissions

`web_permissions.py` is the single server-side role grant mapping. The browser middleware reads the current role from the existing `users` record on every request. `/api/auth/me` reports that role and its effective grants. Page links use the same server-derived grants. Unknown roles have no product access. Route permissions and CSRF checks remain authoritative for direct API calls.

| Role | Chat, sessions, feedback, downloads, documents, OCR | Analytics | Knowledge Base page/read | Knowledge Base write | Batch | System | Landing |
| --- | --- | --- | --- | --- | --- | --- | --- |
| admin | Yes | Yes | Yes | Yes | Yes | Yes | `/app` |
| user | Yes | No | No | No | No | No | `/app` |
| moderator | Yes | No | No | No | No | No | `/app` |
| analytics_viewer | No | Yes | No | No | No | No | `/analytics` |
| knowledge_editor | No | No | Yes | Yes | No | No | `/knowledge-base/` |
| dashboard_viewer | Yes | Yes | Yes | No | No | No | `/app` |
| Unknown role | No | No | No | No | No | No | `/access-denied` |

The exact grants are:

- `admin`: `chat`, `sessions`, `feedback`, `downloads`, `documents`, `ocr`, `analytics`, `kb_page`, `kb_read`, `kb_write`, `batch`, `system`.
- `user` and `moderator`: `chat`, `sessions`, `feedback`, `downloads`, `documents`, `ocr`. Moderator currently has the same grants as user.
- `analytics_viewer`: `analytics`.
- `knowledge_editor`: `kb_page`, `kb_read`, `kb_write`.
- `dashboard_viewer`: `chat`, `sessions`, `feedback`, `downloads`, `documents`, `ocr`, `analytics`, `kb_page`, `kb_read`.
- Unknown roles: no grants.

“Read-only” describes Knowledge Base access for `dashboard_viewer`, not chat activity. This role can chat and manage its own sessions and feedback. It can browse Knowledge Base documents, search and read chunks, and inspect version history, but cannot create, update, delete, or revert content.
