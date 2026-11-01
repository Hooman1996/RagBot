# Browser-user operator guide

`scripts/manage_web_users.py` manages browser accounts in the existing PostgreSQL `users` table. It is environment-agnostic: the selected env file determines the database. The same commands, prompts, and checks apply everywhere. By default it reads the checkout root `.env`; pass `--env-file PATH` before the command to select another file. The file must define `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`. No database credentials are printed.

`WEB_ENVIRONMENT` is used elsewhere by RagBot browser/session configuration, but `manage_web_users.py` does not use it to decide whether user management is allowed.

The CLI has no schema, delete, password-reset, bulk-seeding, role-editor, or custom-grant command. Effective permissions come only from the selected role in `web_permissions.py`. The browser middleware reads the current database role for every request. `dashboard_viewer` can chat and browse Knowledge Base read-only; a different permission combination requires a reviewed policy change.

## Create an account from the dashboard

Sign in as an active `admin` and choose **Users / کاربران** in the left sidebar, or open `GET /admin/users`. Knowledge Base has an equivalent link in its existing header. Only admins have the `users_manage` permission. Other supported roles and unknown roles cannot open the page or call `POST /api/admin/users`; hiding a link is not the authorization boundary.

The Add user form requires **Username, Email, Full name, Role, Password, and Confirm password**. Role defaults to `user`; choices come from the server's `ROLE_PERMISSIONS` allowlist. An admin can choose any supported role, including `admin`. There are no custom grants. Creation keeps the acting admin signed in as themselves. The page follows the saved language and theme and supports English and Persian.

Username uses the CLI policy: 1–100 characters, trimmed, with no whitespace or control characters. Email uses the same address validation as the CLI, is trimmed, has no whitespace or control characters, and is at most 255 characters. Full name is trimmed by the dashboard API, required, at most 255 characters, and free of control characters. Username and email case are preserved; existing database equality/uniqueness rules continue to apply. Passwords must be nonempty, contain no NUL, and occupy at most **72 UTF-8 bytes** (bytes, not characters). They are never truncated. Confirmation must match exactly, including Unicode.

The database generates the integer ID. The shared provisioning code generates a UUID and bcrypt hash, sets `is_active=true`, `is_verified=false`, empty settings, and matching UTC creation/update timestamps. `last_login_at` stays unset until login; national code, bio, and avatar remain optional. This uses the current `DatabaseManager`/CLI schema contract, not the legacy initial Alembic migration. **No schema change or migration is necessary.** The existing database user needs INSERT access and access to the users ID sequence, as with CLI creation.

For an authorized browser request, the API accepts exactly these six JSON string fields: `username`, `email`, `full_name`, `role`, `password`, `confirm_password`. It uses the application's existing database configuration, signed session cookie, CSRF token, and origin checks. IDs, hashes, grants, settings, status flags, and timestamps cannot be supplied. Both routes and all authorization/validation responses use `Cache-Control: no-store`.

Success returns **201** with only `user: {id, uuid, username, email, full_name, role, is_active, is_verified}`. The page shows the username, role, and ID and clears both password fields. Invalid input returns **422** with fixed field/error codes, without echoing submitted values. Duplicate username/email returns **409**, including a uniqueness race during insertion; existing accounts are never overwritten. Unauthenticated API requests return **401** (page requests redirect to login), and permission/CSRF/origin failures return **403**. Database failures use the existing safe **503** dependency-error response. If a network failure leaves the outcome uncertain, check the account using the CLI before retrying. Creation request and response bodies are excluded from HTTP logging. Passwords are never placed in URLs or browser storage.

Deploy the Python, templates, and static changes together through the normal release workflow; fingerprinted asset URLs and integrity hashes update automatically. This implementation does not apply schema changes or restart services. Existing CLI workflows below are unchanged.

## Inspect roles and accounts

```sh
python scripts/manage_web_users.py roles
python scripts/manage_web_users.py users
python scripts/manage_web_users.py show --username example_user
```

`roles` needs no env file or database connection. `users` lists up to 100 accounts by default; `users --limit 200` raises the limit (maximum 500). `users` and `show` display IDs, usernames, active status, roles, and effective permissions. They do not display email addresses, password hashes, or other profile data.

To use another configuration file, place `--env-file` before the command. The filename has no special meaning:

```sh
python scripts/manage_web_users.py --env-file /secure/config/ragbot.env users
python scripts/manage_web_users.py --env-file /secure/config/ragbot.env show --username example_user
```

The same option also works with `create` and `set-role`.

## Create a user

Preview first:

```sh
python scripts/manage_web_users.py create --username example_user --email example_user@example.test --full-name "Example User" --role dashboard_viewer
```

After checking the printed target, apply the same command:

```sh
python scripts/manage_web_users.py create --username example_user --email example_user@example.test --full-name "Example User" --role dashboard_viewer --apply
```

The CLI requires an interactive terminal and asks you to type a confirmation naming the operation, username, database, configured host, and server address and port. It then prompts twice for a password using private input. Passwords must be nonempty and at most 72 UTF-8 bytes, without NUL. Never place a password in a command or shell history. The CLI stores only a bcrypt hash compatible with RagBot login. New users receive a UUID, active and unverified status, empty settings, and timestamps. Duplicate usernames or emails are rejected; existing accounts are never overwritten.

For an explicitly selected file, use the same command format:

```sh
python scripts/manage_web_users.py --env-file /secure/config/ragbot.env create --username example_user --email example_user@example.test --full-name "Example User" --role dashboard_viewer --apply
```

## Change a role

Preview, then apply:

```sh
python scripts/manage_web_users.py set-role --username example_user --role analytics_viewer
python scripts/manage_web_users.py set-role --username example_user --role analytics_viewer --apply
python scripts/manage_web_users.py --env-file /secure/config/ragbot.env set-role --username example_user --role analytics_viewer --apply
```

Only the role and updated timestamp change. The CLI rechecks the account and connected database before committing.

## Operator workflow

1. Check that the selected env file points to the intended PostgreSQL database.
2. Run `create` or `set-role` without `--apply` to preview; this makes no database change.
3. Check the printed database name, configured host, and server address and port.
4. Repeat the command with `--apply` in an interactive terminal.
5. Type the requested target-specific confirmation exactly.
6. For `create`, enter the password twice when prompted.
7. Verify the result with `show --username example_user` or `users`.

The CLI completes its preview read before waiting for confirmation and rechecks the target and account in a short write transaction. Failed checks roll back without committing.
