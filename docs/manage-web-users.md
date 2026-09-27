# Development browser-user operator guide

Run `scripts/manage_web_users.py` from the checkout using the project's Python environment. It writes only to the existing PostgreSQL `users` table. It has no schema, delete, password-reset, bulk, role-editor, or custom-grant command. Effective permissions come from the selected role in `web_permissions.py`; the browser middleware reads the current database role for every request. `dashboard_viewer` can chat and has read-only Knowledge Base access. A different permission combination requires a reviewed policy change. Client-supplied role or permission headers do not grant access.

Keep a private **development** `.env` in the checkout, or pass `--env-file /secure/path/to/development.env` before the subcommand. The CLI reads `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` from that file and requires `WEB_ENVIRONMENT=development`. It never prints credentials. The examples below use illustrative target values; replace them with values confirmed independently by the development database operator. A database name by itself is insufficient: verify the server address and port as well. Do not use production or staging targets.

## 1. List roles

```sh
python scripts/manage_web_users.py roles
```

This does not read `.env` or connect to PostgreSQL. Each line shows effective grant identifiers and the landing page.

## 2. Inspect testuser

```sh
python scripts/manage_web_users.py show --username testuser
```

`show` reports only ID, username, active status, role, and effective grants. It requires the private development `.env` and makes a read-only query.

## 3. Create one dashboard_viewer development account

Preview first; this checks for a duplicate username or email without prompting for a password or writing:

```sh
python scripts/manage_web_users.py create --username dashboard_demo --email dashboard_demo@example.test --full-name 'Dashboard Demo' --role dashboard_viewer
```

After independently confirming the development target, apply using its **actual** identity (the values below are examples):

```sh
python scripts/manage_web_users.py create --username dashboard_demo --email dashboard_demo@example.test --full-name 'Dashboard Demo' --role dashboard_viewer --apply --expect-db faq_dev --expect-host 127.0.0.1 --expect-server-address 127.0.0.1 --expect-server-port 5432
```

The CLI displays the connected database name, reported server address and port, and configured host. It requires an exact typed confirmation, then prompts twice using a private password input. Use a fresh password of at least 12 characters and at most 72 UTF-8 bytes. It hashes with bcrypt, matching the current login service. Never place a password in a command or shell history.

## 4. Change testuser's role

Preview the old and proposed new role:

```sh
python scripts/manage_web_users.py set-role --username testuser --role dashboard_viewer
```

Only after positively identifying the development server, apply (replace the sample identity with the verified one):

```sh
python scripts/manage_web_users.py set-role --username testuser --role dashboard_viewer --apply --expect-db faq_dev --expect-host 127.0.0.1 --expect-server-address 127.0.0.1 --expect-server-port 5432
```

The CLI rolls back if the identity, account, or typed confirmation changes or fails. It commits one account change per apply command.

## 5. Verify

```sh
python scripts/manage_web_users.py show --username testuser
```

After signing in through the development browser app on port 7000, inspect `GET http://localhost:7000/api/auth/me` in DevTools. Confirm `role` is `dashboard_viewer`, `landing_path` is `/app`, and the effective grants are `analytics`, `chat`, `documents`, `downloads`, `feedback`, `kb_page`, `kb_read`, `ocr`, and `sessions`. Confirm `kb_write`, `batch`, and `system` are absent. The chat page should link to Analytics and Knowledge Base, and Knowledge Base should show the Persian read-only indicator and no write controls.
