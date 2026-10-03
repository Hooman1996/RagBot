# Browser-user operator guide

`scripts/manage_web_users.py` manages browser accounts in the existing PostgreSQL `users` table. It is environment-agnostic: the selected env file determines the database. The same commands, prompts, and checks apply everywhere. By default it reads the checkout root `.env`; pass `--env-file PATH` before the command to select another file. The file must define `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`. No database credentials are printed.

`WEB_ENVIRONMENT` is used elsewhere by RagBot browser/session configuration, but `manage_web_users.py` does not use it to decide whether user management is allowed.

The CLI has no schema, delete, password-reset, bulk-seeding, role-editor, or custom-grant command. Effective permissions come only from the selected role in `web_permissions.py`. The browser middleware reads the current database role for every request. `dashboard_viewer` can chat and browse Knowledge Base read-only; a different permission combination requires a reviewed policy change.

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
