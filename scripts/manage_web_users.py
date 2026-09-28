#!/usr/bin/env python3
"""Provision browser users in the existing users table. Run from this checkout.

Roles define permissions in web_permissions.py. dashboard_viewer can chat and
browse Knowledge Base read-only. New permission combinations require a reviewed
policy change, not a client-supplied grant or header.
"""

from __future__ import annotations

import argparse
import getpass
import hmac
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
from uuid import uuid4

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / '.env'
sys.path.insert(0, str(ROOT))
from web_permissions import ROLE_PERMISSIONS, landing_for  # noqa: E402


class CliError(Exception):
    """An operator-safe error message (never contains credentials)."""


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes rejected arguments, which could include a secret.
        self.exit(2, "Invalid command-line arguments; see --help.\n")


def build_parser():
    parser = SafeParser(
        description=("Manage existing-table browser users. Permissions come only from "
                     "the chosen role. dashboard_viewer can chat and has read-only "
                     "Knowledge Base access; new permission combinations require a "
                     "reviewed change to web_permissions.py. Passwords are prompted "
                     "privately and are never accepted as arguments."),
    )
    sub = parser.add_subparsers(dest='command', required=True, parser_class=SafeParser)
    sub.add_parser('roles', help='List roles, effective permissions, and landing paths; no DB connection')
    users = sub.add_parser('users', help='List browser accounts with roles and effective permissions')
    users.add_argument('--limit', type=int, default=100, help='Maximum accounts to show (1–500; default: 100)')
    show = sub.add_parser('show', help='Show one browser account without secrets')
    show.add_argument('--username', required=True)
    create = sub.add_parser('create', help='Preview creation by default; --apply prompts twice for password')
    create.add_argument('--username', required=True)
    create.add_argument('--email', required=True)
    create.add_argument('--full-name', required=True)
    create.add_argument('--role', required=True, choices=sorted(ROLE_PERMISSIONS))
    change = sub.add_parser('set-role', help='Preview an existing account role change by default')
    change.add_argument('--username', required=True)
    change.add_argument('--role', required=True, choices=sorted(ROLE_PERMISSIONS))
    for item in (create, change):
        item.add_argument('--apply', action='store_true', help='Commit after reviewing the .env target and typing confirmation')
    return parser


def validate_text(value, label, maximum, *, spaces=False):
    if not value or value != value.strip() or len(value) > maximum or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise CliError(f'{label} must be nonempty, trimmed, free of control characters, and at most {maximum} characters.')
    if not spaces and any(c.isspace() for c in value):
        raise CliError(f'{label} cannot contain whitespace.')
    return value


def validate_username(value):
    return validate_text(value, 'Username', 100)


def validate_email(value):
    validate_text(value, 'Email', 255)
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', value):
        raise CliError('Email must have one address and domain.')
    return value


def validate_password(value):
    # bcrypt checks only the first 72 UTF-8 bytes on supported versions.
    if len(value) < 12 or len(value.encode('utf-8')) > 72 or '\x00' in value:
        raise CliError('Password must be at least 12 characters and at most 72 UTF-8 bytes, without NUL.')
    return value


def prompt_password():
    first = getpass.getpass('New password: ')
    second = getpass.getpass('Repeat password: ')
    if not hmac.compare_digest(first, second):
        raise CliError('Password entries do not match.')
    return validate_password(first)


def hash_password(password):
    import bcrypt
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('ascii')


def load_config(path=None):
    path = path or ENV_FILE
    if not path.is_file():
        raise CliError('Private .env file is unavailable.')
    values = dotenv_values(path)
    required = ('POSTGRES_HOST', 'POSTGRES_PORT', 'POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD')
    if any(not values.get(key) for key in required):
        raise CliError('Private .env is missing required POSTGRES_* configuration.')
    if values.get('WEB_ENVIRONMENT', '').lower() != 'development':
        raise CliError('Only a .env explicitly marked WEB_ENVIRONMENT=development is supported.')
    try:
        port = int(values['POSTGRES_PORT'])
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise CliError('POSTGRES_PORT is invalid.') from None
    return {key: values[key] for key in required}


def connect(config):
    import psycopg2
    return psycopg2.connect(host=config['POSTGRES_HOST'], port=config['POSTGRES_PORT'],
                            dbname=config['POSTGRES_DB'], user=config['POSTGRES_USER'],
                            password=config['POSTGRES_PASSWORD'], connect_timeout=5,
                            options='-c statement_timeout=10000 -c lock_timeout=3000')


def database_identity(conn, config):
    with conn.cursor() as cursor:
        cursor.execute('SELECT current_database(), inet_server_addr()::text, inet_server_port()')
        database, address, port = cursor.fetchone()
    identity = (database, address, port, config['POSTGRES_HOST'])
    print(f'Database: {database}; server: {address or "unavailable"}:{port or "unavailable"}; configured host: {config["POSTGRES_HOST"]}')
    return identity


def verify_identity(identity, config):
    actual_db, actual_address, actual_port, actual_host = identity
    if (not actual_address or actual_db != config['POSTGRES_DB'] or
            actual_port != int(config['POSTGRES_PORT']) or
            actual_host != config['POSTGRES_HOST']):
        raise CliError('Connected PostgreSQL target does not match the development .env.')


def confirmation(command, username):
    if not sys.stdin.isatty():
        raise CliError('Apply requires an interactive terminal for typed confirmation.')
    phrase = f'{command} {username}'
    print(f'Type exactly: {phrase}')
    if input('Confirmation: ') != phrase:
        raise CliError('Confirmation did not match; no change committed.')


def fetch_account(conn, username, *, lock=False):
    sql = 'SELECT id, username, is_active, role FROM users WHERE username = %s'
    if lock:
        sql += ' FOR UPDATE'
    with conn.cursor() as cursor:
        cursor.execute(sql, (username,))
        return cursor.fetchone()


def fetch_users(conn, limit):
    with conn.cursor() as cursor:
        cursor.execute('SELECT id, username, is_active, role FROM users ORDER BY id LIMIT %s', (limit,))
        return cursor.fetchall()


def print_account(row):
    if row is None:
        raise CliError('Account not found.')
    user_id, username, active, role = row
    permissions = ', '.join(sorted(ROLE_PERMISSIONS.get(role, ()))) or '(none)'
    print(f'ID: {user_id}; username: {username}; active: {active}; role: {role}; permissions: {permissions}')


def check_duplicate(conn, username, email):
    with conn.cursor() as cursor:
        cursor.execute('SELECT username, email FROM users WHERE username = %s OR email = %s',
                       (username, email))
        rows = cursor.fetchall()
    if any(row[0] == username for row in rows):
        raise CliError('Username already exists.')
    if any(row[1] == email for row in rows):
        raise CliError('Email already exists.')


def duplicate_error(exc):
    if getattr(exc, 'pgcode', None) != '23505':
        return None
    constraint = getattr(getattr(exc, 'diag', None), 'constraint_name', '') or ''
    if 'username' in constraint:
        return CliError('Username already exists.')
    if 'email' in constraint:
        return CliError('Email already exists.')
    return CliError('Account conflicts with an existing record.')


def run_database_command(args):
    username = validate_username(args.username) if args.command != 'users' else None
    if args.command == 'users' and not 1 <= args.limit <= 500:
        raise CliError('Limit must be between 1 and 500.')
    if args.command == 'create':
        validate_email(args.email)
        validate_text(args.full_name, 'Full name', 255, spaces=True)
    config = load_config()
    print(f'Configuration: {ENV_FILE}')
    conn = None
    try:
        conn = connect(config)
        identity = database_identity(conn, config)
        if args.command in ('create', 'set-role') and args.apply:
            verify_identity(identity, config)
        if args.command == 'show':
            row = fetch_account(conn, username)
            print_account(row)
            return
        if args.command == 'users':
            rows = fetch_users(conn, args.limit)
            for row in rows:
                print_account(row)
            if not rows:
                print('No accounts found.')
            return
        if args.command == 'create':
            check_duplicate(conn, username, args.email)
            print(f'Proposed create: username={username}; role={args.role}; permissions={", ".join(sorted(ROLE_PERMISSIONS[args.role]))}; landing={landing_for(args.role)}')
        else:
            row = fetch_account(conn, username)
            if row is None:
                raise CliError('Account not found.')
            print(f'Proposed role change: username={username}; old role={row[3]}; new role={args.role}; permissions={", ".join(sorted(ROLE_PERMISSIONS[args.role]))}; landing={landing_for(args.role)}')
        # Finish the read transaction before waiting for a person or a password.
        conn.rollback()
        if not args.apply:
            print('Dry run: no change committed. Use --apply to confirm this .env target and proceed.')
            return
        confirmation(args.command, username)
        password_hash = hash_password(prompt_password()) if args.command == 'create' else None
        # Start a fresh, short transaction and recheck the target and account.
        verify_identity(database_identity(conn, config), config)
        if args.command == 'create':
            check_duplicate(conn, username, args.email)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            with conn.cursor() as cursor:
                cursor.execute('''INSERT INTO users
                    (uuid, email, username, password_hash, full_name, role,
                     is_active, is_verified, settings, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, TRUE, FALSE, %s::jsonb, %s, %s)
                    RETURNING id''',
                    (str(uuid4()), args.email, username, password_hash, args.full_name,
                     args.role, '{}', now, now))
                created_id = cursor.fetchone()[0]
            conn.commit()
            print(f'Created account ID {created_id}; role={args.role}.')
        else:
            current = fetch_account(conn, username, lock=True)
            if current is None or current[0] != row[0] or current[3] != row[3]:
                raise CliError('Account changed since preview; retry from the beginning.')
            with conn.cursor() as cursor:
                cursor.execute('UPDATE users SET role = %s, updated_at = %s WHERE id = %s',
                               (args.role, datetime.now(timezone.utc).replace(tzinfo=None), current[0]))
                if cursor.rowcount != 1:
                    raise CliError('Account changed before update; no change committed.')
            conn.commit()
            print(f'Updated username={username}; old role={row[3]}; new role={args.role}.')
    except CliError:
        if conn:
            conn.rollback()
        raise
    except Exception as exc:
        if conn:
            conn.rollback()
        duplicate = duplicate_error(exc)
        if duplicate:
            raise duplicate from None
        # Database and bcrypt exceptions can contain connection details or inputs.
        raise CliError('Database or password operation failed; no change committed.') from None
    finally:
        if conn:
            conn.close()


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == 'roles':
        for role in sorted(ROLE_PERMISSIONS):
            print(f'{role}: permissions={", ".join(sorted(ROLE_PERMISSIONS[role]))}; landing={landing_for(role)}')
        return 0
    try:
        run_database_command(args)
        return 0
    except CliError as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
