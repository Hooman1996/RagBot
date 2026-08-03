import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional


sys.path.insert(0, str(Path(__file__).parent))

# ═══════════════════════════════════════════════════════════
# IMPORTS
# ═══════════════════════════════════════════════════════════

# Database clients
import psycopg2
import psycopg2.extras

# Services
import bcrypt
from utils.service_errors import ServiceUnavailableError


class AuthenticationService:
    """Handle user authentication"""

    def __init__(self, db_manager):
        self.db_manager = db_manager

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate user

        Args:
            username: Username
            password: Password

        Returns:
            User info dict if successful, None otherwise
        """
        conn = None
        cursor = None
        try:
            # Authentication is called through the bounded blocking runner.  A
            # fresh connection is therefore created and used entirely within
            # that worker thread instead of sharing one psycopg2 connection
            # across concurrent requests.
            conn = self.db_manager.get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Get user by username
            cursor.execute("""
                           SELECT id,
                                  uuid,
                                  username,
                                  email,
                                  password_hash,
                                  full_name,
                                  role,
                                  is_active,
                                  is_verified
                           FROM users
                           WHERE username = %s
                           """, (username,))

            user = cursor.fetchone()

            if not user:
                return None

            # Check if user is active
            if not user['is_active']:
                return None

            # Verify password
            password_hash = user['password_hash']

            if not bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
                return None

            # Update last login
            cursor.execute("""
                           UPDATE users
                           SET last_login_at = %s
                           WHERE id = %s
                           """, (datetime.utcnow(), user['id']))

            conn.commit()

            return dict(user)

        except psycopg2.Error as exc:
            if conn:
                conn.rollback()
            raise ServiceUnavailableError(
                "PostgreSQL operation failed"
            ) from exc
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
