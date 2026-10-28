"""Non-interactive browser-account provisioning shared by HTTP and the operator CLI."""
from __future__ import annotations

import hmac
import re
from datetime import datetime, timezone
from uuid import uuid4

from utils.service_errors import ServiceUnavailableError
from web_permissions import ROLE_PERMISSIONS


class AccountError(Exception):
    """Only static, operator-safe messages may be used here."""


class AccountValidationError(AccountError):
    def __init__(self, field, code, message):
        super().__init__(message)
        self.field = field
        self.code = code


class DuplicateAccountError(AccountError):
    def __init__(self, field=None):
        self.field = field
        super().__init__(f'{field.capitalize()} already exists.' if field else
                         'Account conflicts with an existing record.')


def validate_text(value, label, maximum, *, spaces=False):
    if (not isinstance(value, str) or not value or value != value.strip() or
            len(value) > maximum or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise AccountError(f'{label} must be nonempty, trimmed, free of control characters, and at most {maximum} characters.')
    if not spaces and any(c.isspace() for c in value):
        raise AccountError(f'{label} cannot contain whitespace.')
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise AccountError(f'{label} must contain valid Unicode.') from None
    return value


def validate_username(value):
    return validate_text(value, 'Username', 100)


def validate_email(value):
    validate_text(value, 'Email', 255)
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', value):
        raise AccountError('Email must have one address and domain.')
    return value


def validate_password(value):
    try:
        valid = isinstance(value, str) and value and '\x00' not in value and len(value.encode('utf-8')) <= 72
    except UnicodeError:
        valid = False
    if not valid:
        raise AccountError('Password must be nonempty and at most 72 UTF-8 bytes, without NUL.')
    return value


def confirm_password(first, second):
    validate_password(first)
    try:
        matches = isinstance(second, str) and hmac.compare_digest(first.encode('utf-8'), second.encode('utf-8'))
    except UnicodeError:
        matches = False
    if not matches:
        raise AccountError('Password entries do not match.')
    return first


def hash_password(password):
    import bcrypt
    validate_password(password)
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('ascii')


CREATION_FIELDS = frozenset({'username', 'email', 'full_name', 'role', 'password', 'confirm_password'})


def validate_creation(data):
    # Do not use FastAPI's default validation errors: their input/context may echo secrets.
    if type(data) is not dict or set(data) != CREATION_FIELDS or any(type(v) is not str for v in data.values()):
        raise AccountValidationError('form', 'fields', 'Supply only the six documented text fields.')
    result = dict(data)
    for field, validator in (('username', validate_username), ('email', validate_email),
                             ('full_name', lambda v: validate_text(v.strip(), 'Full name', 255, spaces=True)),
                             ('password', validate_password)):
        try:
            result[field] = validator(data[field])
        except AccountError as exc:
            raise AccountValidationError(field, field, str(exc)) from None
    if data['role'] not in ROLE_PERMISSIONS:
        raise AccountValidationError('role', 'role', 'Choose a supported role.')
    try:
        confirm_password(data['password'], data['confirm_password'])
    except AccountError:
        raise AccountValidationError('confirm_password', 'confirm_password', 'Password entries do not match.') from None
    return result


def check_duplicate(conn, username, email):
    with conn.cursor() as cursor:
        cursor.execute('SELECT username, email FROM users WHERE username = %s OR email = %s', (username, email))
        rows = cursor.fetchall()
    if any(row[0] == username for row in rows):
        raise DuplicateAccountError('username')
    if any(row[1] == email for row in rows):
        raise DuplicateAccountError('email')


def duplicate_error(exc):
    if getattr(exc, 'pgcode', None) != '23505':
        return None
    constraint = getattr(getattr(exc, 'diag', None), 'constraint_name', '') or ''
    for field in ('username', 'email'):
        if field in constraint:
            return DuplicateAccountError(field)
    return DuplicateAccountError()


def insert_account(conn, *, username, email, full_name, role, password_hash):
    """Caller owns the short transaction; id/defaults match the active provisioning contract."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # existing TIMESTAMP columns store UTC
    account_uuid = str(uuid4())
    with conn.cursor() as cursor:
        cursor.execute('''INSERT INTO users
            (uuid, email, username, password_hash, full_name, role,
             is_active, is_verified, settings, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, FALSE, %s::jsonb, %s, %s)
            RETURNING id''',
            (account_uuid, email, username, password_hash, full_name, role, '{}', now, now))
        created_id = cursor.fetchone()[0]
    return {'id': created_id, 'uuid': account_uuid, 'username': username, 'email': email,
            'full_name': full_name, 'role': role, 'is_active': True, 'is_verified': False}


def create_browser_account(db, data):
    """Run entirely in the bounded worker, hashing before acquiring a connection."""
    conn = None
    try:
        password_hash = hash_password(data['password'])
        conn = db.get_connection()
        check_duplicate(conn, data['username'], data['email'])
        summary = insert_account(conn, username=data['username'], email=data['email'],
                                 full_name=data['full_name'], role=data['role'], password_hash=password_hash)
        conn.commit()
        return summary
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass  # always attempt close, and never surface driver details
        duplicate = exc if isinstance(exc, DuplicateAccountError) else duplicate_error(exc)
        if duplicate:
            raise duplicate from None
        raise ServiceUnavailableError('Browser account creation failed') from None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                raise ServiceUnavailableError('PostgreSQL cleanup failed') from None
