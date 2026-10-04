"""Isolated CLI tests; these fakes never open the configured database."""
from io import StringIO
from pathlib import Path
import re
import sys

import bcrypt
import pytest

from scripts import manage_web_users as cli
from web_permissions import ROLE_PERMISSIONS, landing_for


class InputTTY:
    def isatty(self):
        return True


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.result = None
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def execute(self, sql, params=None):
        self.connection.queries.append((sql, params))
        if 'current_database()' in sql:
            self.result = ('faq_dev', '127.0.0.1', 5432)
        elif 'SELECT username, email FROM users' in sql:
            self.result = [row for row in self.connection.users.values()
                           if row['username'] == params[0] or row['email'] == params[1]]
        elif 'SELECT id, username, is_active, role FROM users ORDER BY id LIMIT' in sql:
            self.result = [(row['id'], row['username'], row['active'], row['role'])
                           for row in list(self.connection.users.values())[:params[0]]]
        elif 'SELECT id, username, is_active, role FROM users' in sql:
            row = self.connection.users.get(params[0])
            self.result = (row['id'], row['username'], row['active'], row['role']) if row else None
        elif 'INSERT INTO users' in sql:
            self.connection.pending = ('create', params)
            self.result = (3,)
        elif 'UPDATE users SET role' in sql:
            self.connection.pending = ('set-role', params)
            self.rowcount = 1
        else:
            raise AssertionError('Unexpected SQL')

    def fetchone(self):
        return self.result

    def fetchall(self):
        if self.result and isinstance(self.result[0], tuple):
            return self.result
        return [(row['username'], row['email']) for row in self.result]


class FakeConnection:
    def __init__(self, users=None):
        self.users = users or {}
        self.queries = []
        self.pending = None
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1
        if self.pending and self.pending[0] == 'create':
            params = self.pending[1]
            self.users[params[2]] = {'id': 3, 'username': params[2], 'email': params[1],
                                      'active': True, 'role': params[5], 'hash': params[3]}
        if self.pending and self.pending[0] == 'set-role':
            self.users['testuser']['role'] = self.pending[1][0]
        self.pending = None

    def rollback(self):
        self.rollbacks += 1
        self.pending = None

    def close(self):
        self.closed = True


@pytest.fixture
def environment(tmp_path, monkeypatch):
    path = tmp_path / '.env'
    path.write_text('WEB_ENVIRONMENT=development\nPOSTGRES_HOST=localhost\nPOSTGRES_PORT=5432\n'
                    'POSTGRES_DB=faq_dev\nPOSTGRES_USER=test_role\nPOSTGRES_PASSWORD=test_only\n')
    conn = FakeConnection({'testuser': {'id': 1, 'username': 'testuser',
                                        'email': 'testuser@example.test', 'active': True, 'role': 'user'}})
    monkeypatch.setattr(cli, 'connect', lambda config: conn)
    monkeypatch.setattr(cli, 'ENV_FILE', path)
    return path, conn


def call(*args):
    return cli.main(list(args))


def confirm(monkeypatch, command, username):
    monkeypatch.setattr(sys, 'stdin', InputTTY())
    monkeypatch.setattr('builtins.input', lambda prompt: f'{command.upper()} {username} ON faq_dev@localhost (server 127.0.0.1:5432)')


def test_roles_uses_policy_without_database(monkeypatch, capsys):
    monkeypatch.setattr(cli, 'connect', lambda config: pytest.fail('roles connected to DB'))
    assert cli.main(['roles']) == 0
    output = capsys.readouterr().out
    assert len(output.splitlines()) == len(ROLE_PERMISSIONS)
    for role, grants in ROLE_PERMISSIONS.items():
        assert f'{role}: permissions={", ".join(sorted(grants))}; landing={landing_for(role)}' in output


@pytest.mark.parametrize('value,label', [('', 'Username'), ('x' * 101, 'Username'),
                                           ('bad name', 'Username'), ('bad\nname', 'Username')])
def test_username_validation(value, label):
    with pytest.raises(cli.CliError, match=label):
        cli.validate_username(value)


@pytest.mark.parametrize('value', ['a@b', 'x' * 256 + '@example.test', 'a b@example.test'])
def test_email_validation(value):
    with pytest.raises(cli.CliError):
        cli.validate_email(value)


def test_create_rejects_unknown_role_and_secret_argument_without_echo(capsys):
    with pytest.raises(SystemExit):
        cli.main(['create', '--username', 'x', '--email', 'x@example.test',
                  '--full-name', 'X', '--role', 'invalid', '--password', 'do-not-echo'])
    assert 'do-not-echo' not in capsys.readouterr().err


def test_password_prompt_and_bcrypt_format(monkeypatch, capsys):
    answers = iter(['GoodPassword123!', 'GoodPassword123!'])
    prompts = []
    monkeypatch.setattr(cli.getpass, 'getpass', lambda label: prompts.append(label) or next(answers))
    password = cli.prompt_password()
    hashed = cli.hash_password(password)
    assert len(prompts) == 2
    assert bcrypt.checkpw(password.encode('utf-8'), hashed.encode('ascii'))
    assert re.match(r'^\$2[aby]\$\d\d\$', hashed)
    assert password not in capsys.readouterr().out
    monkeypatch.setattr(cli.getpass, 'getpass', lambda label: 'different' if 'Repeat' in label else 'GoodPassword123!')
    with pytest.raises(cli.CliError, match='do not match'):
        cli.prompt_password()
    with pytest.raises(cli.CliError, match='72 UTF-8 bytes'):
        cli.validate_password('é' * 37)
    assert cli.validate_password('short') == 'short'
    short_hash = cli.hash_password('short')
    assert bcrypt.checkpw(b'short', short_hash.encode('utf-8'))
    with pytest.raises(cli.CliError, match='nonempty'):
        cli.validate_password('')
    with pytest.raises(cli.CliError, match='NUL'):
        cli.validate_password('abc\x00def')


def test_show_exposes_only_safe_fields(environment, capsys):
    path, conn = environment
    assert call('show', '--username', 'testuser') == 0
    output = capsys.readouterr().out
    assert 'ID: 1' in output and 'role: user' in output and 'permissions: chat' in output
    assert 'testuser@example.test' not in output and 'password_hash' not in output
    assert conn.commits == 0 and conn.closed


def test_create_duplicate_username_and_email_rejected(environment, capsys):
    path, conn = environment
    base = ('create', '--username', 'testuser', '--email', 'new@example.test',
            '--full-name', 'New User', '--role', 'dashboard_viewer')
    assert call(*base) == 1
    assert 'Username already exists' in capsys.readouterr().err
    assert call('create', '--username', 'newuser', '--email', 'testuser@example.test',
                '--full-name', 'New User', '--role', 'dashboard_viewer') == 1
    assert 'Email already exists' in capsys.readouterr().err
    assert conn.commits == 0 and conn.closed


@pytest.mark.parametrize('web_environment', ['development', 'production', 'staging', None])
def test_web_environment_is_ignored(environment, web_environment, capsys):
    path, conn = environment
    content = path.read_text()
    if web_environment is None:
        content = content.replace('WEB_ENVIRONMENT=development\n', '')
    else:
        content = content.replace('WEB_ENVIRONMENT=development', f'WEB_ENVIRONMENT={web_environment}')
    path.write_text(content)
    assert call('users') == 0
    assert 'ID: 1' in capsys.readouterr().out
    assert conn.commits == 0


def test_server_identity_mismatch_rolls_back(environment, monkeypatch, capsys):
    path, conn = environment
    monkeypatch.setattr(cli, 'database_identity', lambda connected, config: ('other_db', '10.0.0.9', 5432, 'localhost'))
    assert call('set-role', '--username', 'testuser', '--role', 'dashboard_viewer',
                '--apply') == 1
    assert 'does not match' in capsys.readouterr().err
    assert conn.commits == 0 and conn.rollbacks == 1 and conn.closed


def test_create_dry_run_rolls_back_without_password_prompt(environment, monkeypatch, capsys):
    path, conn = environment
    monkeypatch.setattr(cli.getpass, 'getpass', lambda label: pytest.fail('dry run prompted for password'))
    assert call('create', '--username', 'newuser', '--email', 'new@example.test',
                '--full-name', 'New User', '--role', 'dashboard_viewer') == 0
    assert 'Dry run' in capsys.readouterr().out
    assert conn.commits == 0 and conn.rollbacks == 1 and conn.closed
    assert not any('INSERT INTO users' in sql for sql, _ in conn.queries)


def test_create_apply_parameterized_insert_and_commit(environment, monkeypatch, capsys):
    path, conn = environment
    username = "x'OR'1=1"
    confirm(monkeypatch, 'create', username)
    prompts = []
    monkeypatch.setattr(cli.getpass, 'getpass', lambda label: prompts.append(label) or 'GoodPassword123!')
    assert call('create', '--username', username, '--email', 'new@example.test',
                '--full-name', 'New User', '--role', 'dashboard_viewer', '--apply') == 0
    output = capsys.readouterr().out
    assert conn.commits == 1 and conn.closed and len(prompts) == 2
    insert, params = next((sql, params) for sql, params in conn.queries if 'INSERT INTO users' in sql)
    assert '%s' in insert and username not in insert and username in params
    assert bcrypt.checkpw(b'GoodPassword123!', params[3].encode('utf-8'))
    assert 'uuid, email, username, password_hash, full_name, role,' in insert
    assert 'is_active, is_verified, settings, created_at, updated_at' in insert
    assert 'TRUE, FALSE, %s::jsonb' in insert
    assert params[1:3] == ('new@example.test', username)
    assert params[4:7] == ('New User', 'dashboard_viewer', '{}')
    assert params[7] == params[8]
    assert params[3] != 'GoodPassword123!'
    assert 'GoodPassword123!' not in output and params[3] not in output
    assert conn.users[username]['role'] == 'dashboard_viewer'


def test_set_role_preview_then_apply_and_recheck(environment, monkeypatch, capsys):
    path, conn = environment
    assert call('set-role', '--username', 'testuser', '--role', 'dashboard_viewer') == 0
    assert conn.commits == 0 and conn.users['testuser']['role'] == 'user'
    assert 'old role=user; new role=dashboard_viewer' in capsys.readouterr().out
    confirm(monkeypatch, 'set-role', 'testuser')
    assert call('set-role', '--username', 'testuser', '--role', 'dashboard_viewer',
                '--apply') == 0
    assert conn.commits == 1 and conn.users['testuser']['role'] == 'dashboard_viewer'
    sql, params = next((sql, params) for sql, params in conn.queries if 'UPDATE users SET role' in sql)
    assert sql.strip() == 'UPDATE users SET role = %s, updated_at = %s WHERE id = %s'
    assert params[0] == 'dashboard_viewer' and params[2] == 1
    assert 'old role=user; new role=dashboard_viewer' in capsys.readouterr().out


def test_typed_confirmation_mismatch_never_writes(environment, monkeypatch, capsys):
    path, conn = environment
    monkeypatch.setattr(sys, 'stdin', InputTTY())
    monkeypatch.setattr('builtins.input', lambda prompt: 'wrong')
    assert call('set-role', '--username', 'testuser', '--role', 'dashboard_viewer',
                '--apply') == 1
    assert conn.commits == 0 and conn.closed
    assert not any('UPDATE users SET role' in sql for sql, _ in conn.queries)
    assert 'Confirmation did not match' in capsys.readouterr().err


def test_missing_env_refuses_before_connect(environment, monkeypatch, capsys):
    path, _ = environment
    path.unlink()
    monkeypatch.setattr(cli, 'connect', lambda config: pytest.fail('connected without .env'))
    assert call('set-role', '--username', 'testuser', '--role', 'dashboard_viewer', '--apply') == 1
    assert '.env file is unavailable' in capsys.readouterr().err


def test_apply_requires_terminal(environment, monkeypatch, capsys):
    path, conn = environment
    monkeypatch.setattr(sys, 'stdin', StringIO('set-role testuser\n'))
    assert call('set-role', '--username', 'testuser', '--role', 'dashboard_viewer',
                '--apply') == 1
    assert 'interactive terminal' in capsys.readouterr().err
    assert conn.commits == 0 and conn.closed


def test_set_role_rejects_account_changed_since_preview(environment, monkeypatch, capsys):
    path, conn = environment
    monkeypatch.setattr(sys, 'stdin', InputTTY())

    def changed_account(prompt):
        conn.users['testuser']['role'] = 'moderator'
        return 'SET-ROLE testuser ON faq_dev@localhost (server 127.0.0.1:5432)'

    monkeypatch.setattr('builtins.input', changed_account)
    assert call('set-role', '--username', 'testuser', '--role', 'dashboard_viewer',
                '--apply') == 1
    assert 'changed since preview' in capsys.readouterr().err
    assert conn.commits == 0 and conn.closed


def test_duplicate_race_error_is_redacted():
    class UniqueError(Exception):
        pgcode = '23505'
        diag = type('Diag', (), {'constraint_name': 'users_email_key'})()

    error = cli.duplicate_error(UniqueError('secret password happened to be in exception'))
    assert isinstance(error, cli.CliError)
    assert str(error) == 'Email already exists.'


def test_apply_sql_failure_rolls_back_and_redacts_exception(environment, monkeypatch, capsys):
    path, conn = environment
    confirm(monkeypatch, 'set-role', 'testuser')
    original_cursor = conn.cursor

    def failing_cursor():
        cursor = original_cursor()
        original_execute = cursor.execute

        def execute(sql, params=None):
            if 'UPDATE users SET role' in sql:
                raise RuntimeError('private database password leaked in driver error')
            return original_execute(sql, params)

        cursor.execute = execute
        return cursor

    monkeypatch.setattr(conn, 'cursor', failing_cursor)
    assert call('set-role', '--username', 'testuser', '--role', 'dashboard_viewer',
                '--apply') == 1
    output = capsys.readouterr()
    assert 'private database password' not in output.out + output.err
    assert 'Database or password operation failed' in output.err
    assert conn.commits == 0 and conn.rollbacks >= 2 and conn.closed


def test_users_lists_only_safe_fields_and_uses_parameterized_limit(environment, capsys):
    path, conn = environment
    assert call('users', '--limit', '1') == 0
    output = capsys.readouterr().out
    assert 'ID: 1' in output and 'role: user' in output
    assert 'testuser@example.test' not in output and 'password_hash' not in output
    sql, params = next((sql, params) for sql, params in conn.queries if 'ORDER BY id LIMIT' in sql)
    assert 'LIMIT %s' in sql and params == (1,)
    assert conn.commits == 0 and conn.closed


def test_users_rejects_excessive_limit_before_connection(environment, monkeypatch, capsys):
    path, _ = environment
    monkeypatch.setattr(cli, 'connect', lambda config: pytest.fail('connected with invalid limit'))
    assert call('users', '--limit', '501') == 1
    assert 'between 1 and 500' in capsys.readouterr().err


@pytest.mark.parametrize('missing', ['POSTGRES_HOST', 'POSTGRES_PASSWORD'])
def test_missing_database_setting_fails_before_connect(environment, monkeypatch, capsys, missing):
    path, _ = environment
    path.write_text('\n'.join(line for line in path.read_text().splitlines()
                              if not line.startswith(missing + '=')) + '\n')
    monkeypatch.setattr(cli, 'connect', lambda config: pytest.fail('connected with incomplete config'))
    assert call('users') == 1
    output = capsys.readouterr()
    assert 'missing required POSTGRES_*' in output.err
    assert 'test_only' not in output.out + output.err


@pytest.mark.parametrize('port', ['abc', '0', '65536'])
def test_invalid_database_port_fails_before_connect(environment, monkeypatch, capsys, port):
    path, _ = environment
    path.write_text(path.read_text().replace('POSTGRES_PORT=5432', f'POSTGRES_PORT={port}'))
    monkeypatch.setattr(cli, 'connect', lambda config: pytest.fail('connected with invalid port'))
    assert call('users') == 1
    assert 'POSTGRES_PORT is invalid' in capsys.readouterr().err


def test_explicit_env_file_is_used_for_read_and_write_commands(environment, tmp_path, monkeypatch, capsys):
    default_path, conn = environment
    explicit_path = tmp_path / 'any-name.conf'
    explicit_path.write_text(default_path.read_text().replace('WEB_ENVIRONMENT=development\n', ''))
    default_path.unlink()
    monkeypatch.setattr(cli, 'connect',
                        lambda config: conn if config['POSTGRES_PASSWORD'] == 'test_only'
                        else pytest.fail('wrong configuration'))
    assert call('--env-file', str(explicit_path), 'users') == 0
    assert call('--env-file', str(explicit_path), 'show', '--username', 'testuser') == 0
    assert call('--env-file', str(explicit_path), 'create', '--username', 'newuser',
                '--email', 'new@example.test', '--full-name', 'New User',
                '--role', 'dashboard_viewer') == 0
    assert call('--env-file', str(explicit_path), 'set-role', '--username', 'testuser',
                '--role', 'dashboard_viewer') == 0
    assert str(explicit_path) in capsys.readouterr().out
    assert conn.commits == 0


def test_roles_ignores_missing_explicit_env_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, 'connect', lambda config: pytest.fail('roles connected to DB'))
    assert call('--env-file', str(tmp_path / 'absent.env'), 'roles') == 0
    assert 'admin:' in capsys.readouterr().out


def test_unknown_role_fails_before_connection(environment, monkeypatch, capsys):
    monkeypatch.setattr(cli, 'connect', lambda config: pytest.fail('connected with unsupported role'))
    with pytest.raises(SystemExit) as result:
        call('set-role', '--username', 'testuser', '--role', 'unreviewed')
    assert result.value.code == 2
    assert 'unreviewed' not in capsys.readouterr().err


def test_confirmation_contains_complete_target(environment, monkeypatch, capsys):
    _, conn = environment
    monkeypatch.setattr(sys, 'stdin', InputTTY())
    monkeypatch.setattr('builtins.input', lambda prompt: 'wrong')
    assert call('set-role', '--username', 'testuser', '--role', 'dashboard_viewer', '--apply') == 1
    output = capsys.readouterr().out
    assert 'Database: faq_dev' in output
    assert 'configured host: localhost' in output
    assert 'server: 127.0.0.1:5432' in output
    assert 'SET-ROLE testuser ON faq_dev@localhost (server 127.0.0.1:5432)' in output
    assert conn.commits == 0


def test_target_change_after_confirmation_rolls_back(environment, monkeypatch, capsys):
    _, conn = environment
    confirm(monkeypatch, 'set-role', 'testuser')
    calls = 0

    def changing_identity(connected, config):
        nonlocal calls
        calls += 1
        if calls == 1:
            return ('faq_dev', '127.0.0.1', 5432, 'localhost')
        return ('faq_dev', '127.0.0.2', 5432, 'localhost')

    monkeypatch.setattr(cli, 'database_identity', changing_identity)
    assert call('set-role', '--username', 'testuser', '--role', 'dashboard_viewer', '--apply') == 1
    assert 'changed since preview' in capsys.readouterr().err
    assert conn.commits == 0 and conn.rollbacks >= 2


def test_password_and_hash_are_redacted_on_failed_insert(environment, monkeypatch, capsys):
    _, conn = environment
    confirm(monkeypatch, 'create', 'newuser')
    monkeypatch.setattr(cli.getpass, 'getpass', lambda prompt: 'GoodPassword123!')
    original_cursor = conn.cursor

    def failing_cursor():
        cursor = original_cursor()
        original_execute = cursor.execute

        def execute(sql, params=None):
            if 'INSERT INTO users' in sql:
                raise RuntimeError(f'failed with {params[3]} and {params[1]} and GoodPassword123! and test_only')
            return original_execute(sql, params)

        cursor.execute = execute
        return cursor

    monkeypatch.setattr(conn, 'cursor', failing_cursor)
    assert call('create', '--username', 'newuser', '--email', 'new@example.test',
                '--full-name', 'New User', '--role', 'dashboard_viewer', '--apply') == 1
    output = capsys.readouterr()
    assert 'Database or password operation failed' in output.err
    assert 'GoodPassword123!' not in output.out + output.err
    assert 'test_only' not in output.out + output.err
    assert '$2' not in output.out + output.err
    assert conn.commits == 0


def test_unavailable_server_address_uses_configured_host_and_server_port(environment, monkeypatch, capsys):
    _, conn = environment
    monkeypatch.setattr(cli, 'database_identity',
                        lambda connected, config: ('faq_dev', None, 5432, 'localhost'))
    monkeypatch.setattr(sys, 'stdin', InputTTY())
    monkeypatch.setattr('builtins.input',
                        lambda prompt: 'SET-ROLE testuser ON faq_dev@localhost (server unavailable:5432)')
    assert call('set-role', '--username', 'testuser', '--role', 'dashboard_viewer', '--apply') == 0
    assert 'server unavailable:5432' in capsys.readouterr().out
    assert conn.commits == 1
