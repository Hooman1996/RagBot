# new_architecture/app/services/history/database.py

import json
import psycopg2
import psycopg2.extras
from datetime import datetime
import uuid

import os
from dotenv import load_dotenv
from utils.service_errors import ServiceUnavailableError

# Load variables from .env into os.environ
load_dotenv()
# ==================== DATABASE MANAGER ====================

# ==================== DATABASE MANAGER ====================

class DatabaseManager:
    """
    Raw psycopg2 PostgreSQL operations.
    Strictly aligned with the SQLAlchemy User / ChatSession / Query models.
    All NOT NULL fields are supplied explicitly on every INSERT.
    """

    def __init__(self, host=os.getenv("POSTGRES_HOST"), port=os.getenv("POSTGRES_PORT"), dbname=os.getenv("POSTGRES_DB"),
                 user=os.getenv("POSTGRES_USER"), password=os.getenv("POSTGRES_PASSWORD"),
                 connect_timeout: int = 5, statement_timeout_ms: int = 10_000,
                 lock_timeout_ms: int = 3_000):
        self.conn_params = {
            "host": host, "port": port, "dbname": dbname,
            "user": user, "password": password,
            "connect_timeout": connect_timeout,
            "options": (
                f"-c statement_timeout={statement_timeout_ms} "
                f"-c lock_timeout={lock_timeout_ms}"
            ),
        }

    # ─────────────────────────────────────────────────────────────
    # Connection / execution core
    # ─────────────────────────────────────────────────────────────

    def get_connection(self):
        conn = psycopg2.connect(**self.conn_params)
        conn.autocommit = False
        return conn

    def _execute(self, query: str, params=None, fetch: str = None):
        """
        fetch=None   → write operation, commits, returns True/False
        fetch="one"  → SELECT … RETURNING, commits, returns dict | None
        fetch="all"  → SELECT, returns list[dict]
        """
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, params)
                if fetch == "one":
                    result = cur.fetchone()
                    conn.commit()
                    return dict(result) if result else None
                if fetch == "all":
                    result = cur.fetchall()
                    conn.commit()
                    return [dict(r) for r in result] if result else []
                # write path
                conn.commit()
                return True
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise ServiceUnavailableError(
                "PostgreSQL operation failed"
            ) from e
        finally:
            if conn:
                conn.close()

    # ─────────────────────────────────────────────────────────────
    # Schema bootstrap
    # ─────────────────────────────────────────────────────────────

    def init_db(self):
        """Creates tables and indexes if they don't exist."""

        self._execute("""
        CREATE TABLE IF NOT EXISTS users (
            id              SERIAL PRIMARY KEY,
            uuid            VARCHAR(36) UNIQUE NOT NULL,
            email           VARCHAR(255) UNIQUE NOT NULL,
            username        VARCHAR(100) UNIQUE NOT NULL,
            password_hash   VARCHAR(255) NOT NULL,
            full_name       VARCHAR(255),
            bio             TEXT,
            avatar_url      VARCHAR(500),
            role            VARCHAR(50)  NOT NULL DEFAULT 'user',
            is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
            is_verified     BOOLEAN      NOT NULL DEFAULT FALSE,
            settings        JSONB        NOT NULL DEFAULT '{}',
            created_at      TIMESTAMP    NOT NULL,
            updated_at      TIMESTAMP    NOT NULL,
            last_login_at   TIMESTAMP
        );
        """)

        self._execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id               SERIAL PRIMARY KEY,
            uuid             VARCHAR(36)  UNIQUE NOT NULL,
            user_id          INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title            VARCHAR(255),
            description      TEXT,
            model_name       VARCHAR(100),
            temperature      FLOAT        NOT NULL DEFAULT 0.7,
            settings         JSONB        NOT NULL DEFAULT '{}',
            query_count      INTEGER      NOT NULL DEFAULT 0,
            total_tokens     INTEGER      NOT NULL DEFAULT 0,
            status           VARCHAR(50)  NOT NULL DEFAULT 'active',
            is_pinned        BOOLEAN      NOT NULL DEFAULT FALSE,
            meta_data        JSONB        NOT NULL DEFAULT '{}',
            created_at       TIMESTAMP    NOT NULL,
            updated_at       TIMESTAMP    NOT NULL,
            last_activity_at TIMESTAMP    NOT NULL
        );
        """)

        self._execute("""
        CREATE TABLE IF NOT EXISTS queries (
            id                  SERIAL PRIMARY KEY,
            uuid                VARCHAR(36)  UNIQUE NOT NULL,
            user_id             INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            chat_session_id     INTEGER      REFERENCES chat_sessions(id) ON DELETE CASCADE,
            query_text          TEXT         NOT NULL,
            response_text       TEXT,
            query_type          VARCHAR(50)  NOT NULL DEFAULT 'question',
            language            VARCHAR(10)  NOT NULL DEFAULT 'en',
            retrieved_chunks    JSONB        NOT NULL DEFAULT '[]',
            retrieved_documents JSONB        NOT NULL DEFAULT '[]',
            retrieval_method    VARCHAR(50),
            response_time       FLOAT,
            token_count         INTEGER,
            relevance_score     FLOAT,
            model_name          VARCHAR(100),
            embedding_model     VARCHAR(100),
            temperature         FLOAT,
            status              VARCHAR(50)  NOT NULL DEFAULT 'completed',
            is_helpful          INTEGER,
            has_sources         INTEGER      NOT NULL DEFAULT 0,
            meta_data           JSONB        NOT NULL DEFAULT '{}',
            error_message       TEXT,
            created_at          TIMESTAMP    NOT NULL,
            updated_at          TIMESTAMP    NOT NULL,
            completed_at        TIMESTAMP
        );
        """)

        self._execute("""
        CREATE TABLE IF NOT EXISTS mass_answer_jobs (
            id                  VARCHAR(36) PRIMARY KEY,
            status              VARCHAR(32) NOT NULL,
            input_filename      TEXT NOT NULL,
            input_format        VARCHAR(8) NOT NULL,
            selected_documents  JSONB NOT NULL DEFAULT '[]',
            artifact_directory  TEXT NOT NULL,
            result_path         TEXT,
            total_rows          INTEGER NOT NULL DEFAULT 0,
            valid_rows          INTEGER NOT NULL DEFAULT 0,
            completed_rows      INTEGER NOT NULL DEFAULT 0,
            successful_rows     INTEGER NOT NULL DEFAULT 0,
            failed_rows         INTEGER NOT NULL DEFAULT 0,
            timed_out_rows      INTEGER NOT NULL DEFAULT 0,
            error_message       TEXT,
            created_at          TIMESTAMP NOT NULL,
            started_at          TIMESTAMP,
            completed_at        TIMESTAMP,
            expires_at          TIMESTAMP NOT NULL,
            updated_at          TIMESTAMP NOT NULL
        );
        """)

        self._execute("""
        CREATE TABLE IF NOT EXISTS knowledge_document_revisions (
            document_id INTEGER PRIMARY KEY
                REFERENCES documents(id) ON DELETE CASCADE,
            revision BIGINT NOT NULL DEFAULT 0,
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        );
        """)

        for ddl in [
            "ALTER TABLE mass_answer_jobs ADD COLUMN IF NOT EXISTS total_duration_ms FLOAT;",
            "ALTER TABLE mass_answer_jobs ADD COLUMN IF NOT EXISTS average_row_ms FLOAT;",
            "ALTER TABLE mass_answer_jobs ADD COLUMN IF NOT EXISTS p50_row_ms FLOAT;",
            "ALTER TABLE mass_answer_jobs ADD COLUMN IF NOT EXISTS p95_row_ms FLOAT;",
            "ALTER TABLE mass_answer_jobs ADD COLUMN IF NOT EXISTS p99_row_ms FLOAT;",
        ]:
            self._execute(ddl)

        for ddl in [
            "CREATE INDEX IF NOT EXISTS idx_user_created    ON queries(user_id, created_at);",
            "CREATE INDEX IF NOT EXISTS idx_session_created ON queries(chat_session_id, created_at);",
            "CREATE INDEX IF NOT EXISTS idx_status          ON queries(status);",
            "CREATE INDEX IF NOT EXISTS idx_sessions_user   ON chat_sessions(user_id, last_activity_at DESC);",
            "CREATE INDEX IF NOT EXISTS idx_mass_jobs_expiry ON mass_answer_jobs(expires_at);",
        ]:
            self._execute(ddl)

    def create_mass_answer_job(self, job: dict) -> dict | None:
        return self._execute("""
        INSERT INTO mass_answer_jobs (
            id, status, input_filename, input_format, selected_documents,
            artifact_directory, total_rows, valid_rows,
            created_at, expires_at, updated_at
        ) VALUES (%s, 'queued', %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *;
        """, (
            job["id"], job["input_filename"], job["input_format"],
            json.dumps(job["selected_documents"], ensure_ascii=False),
            job["artifact_directory"], job["total_rows"], job["valid_rows"],
            job["created_at"], job["expires_at"], job["created_at"],
        ), fetch="one")

    def get_mass_answer_job(self, job_id: str) -> dict | None:
        return self._execute(
            "SELECT * FROM mass_answer_jobs WHERE id = %s",
            (job_id,), fetch="one"
        )

    def update_mass_answer_job(self, job_id: str, fields: dict) -> None:
        allowed = {
            "status", "result_path", "completed_rows", "successful_rows",
            "failed_rows", "timed_out_rows", "error_message", "started_at",
            "completed_at",
            "total_duration_ms", "average_row_ms", "p50_row_ms",
            "p95_row_ms", "p99_row_ms",
        }
        updates = [(key, value) for key, value in fields.items() if key in allowed]
        if not updates:
            return
        assignments = ", ".join(f"{key} = %s" for key, _ in updates)
        params = [value for _, value in updates]
        params.extend([datetime.utcnow(), job_id])
        self._execute(
            f"UPDATE mass_answer_jobs SET {assignments}, updated_at = %s WHERE id = %s",
            tuple(params),
        )

    def delete_mass_answer_job(self, job_id: str) -> None:
        self._execute("DELETE FROM mass_answer_jobs WHERE id = %s", (job_id,))

    def get_expired_mass_answer_jobs(self, now: datetime) -> list[dict]:
        return self._execute(
            "SELECT * FROM mass_answer_jobs WHERE expires_at <= %s",
            (now,), fetch="all"
        )

    # ─────────────────────────────────────────────────────────────
    # Users
    # ─────────────────────────────────────────────────────────────

    def get_user_by_id(self, user_id: int) -> dict | None:
        return self._execute(
            "SELECT * FROM users WHERE id = %s",
            (user_id,), fetch="one"
        )

    def get_user_by_username(self, username: str) -> dict | None:
        return self._execute(
            "SELECT * FROM users WHERE username = %s",
            (username,), fetch="one"
        )

    def upsert_user(self, user_id: int, username: str, email: str = None) -> None:
        """Insert or update a user (used after external auth)."""
        import uuid as _uuid
        now = datetime.utcnow()
        self._execute("""
        INSERT INTO users (id, uuid, email, username, password_hash,
                           role, is_active, is_verified, settings,
                           created_at, updated_at)
        VALUES (%s, %s, %s, %s, '', 'user', TRUE, FALSE, '{}', %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            username   = EXCLUDED.username,
            updated_at = EXCLUDED.updated_at;
        """, (
            user_id,
            str(_uuid.uuid4()),
            email or f"{username}@placeholder.local",
            username,
            now, now,
        ))

    def get_or_create_user_by_national_code(self, national_code: str) -> dict | None:
        """
        Just-In-Time (JIT) Provisioning: Fetches user by national_code.
        If they do not exist, seamlessly creates a background profile.
        """
        # 1. Try to find the user first (Fast Path)
        user = self._execute(
            "SELECT * FROM users WHERE national_code = %s",
            (str(national_code),), fetch="one"
        )
        if user:
            return user

        # 2. If not found, create a new profile (JIT Provisioning)
        import uuid as _uuid
        now = datetime.utcnow()
        new_uuid = str(_uuid.uuid4())

        # Generate safe placeholder data to satisfy legacy NOT NULL constraints
        placeholder_username = f"app_user_{national_code}"
        placeholder_email = f"{national_code}@hibank.local"

        try:
            # Insert the new user and return the newly generated row
            new_user = self._execute("""
                                     INSERT INTO users (uuid, national_code, email, username, password_hash,
                                                        role, is_active, is_verified, settings, created_at, updated_at)
                                     VALUES (%s, %s, %s, %s, '',
                                             'user', TRUE, TRUE, '{}', %s, %s) RETURNING *;
                                     """, (
                                         new_uuid, str(national_code), placeholder_email, placeholder_username,
                                         now, now
                                     ), fetch="one")

            return new_user

        except Exception:
            # Fallback: If two requests from the same new user hit at the exact
            # same millisecond, a race condition occurs. We catch the conflict and fetch.
            return self._execute(
                "SELECT * FROM users WHERE national_code = %s",
                (str(national_code),), fetch="one"
            )
    # ─────────────────────────────────────────────────────────────
    # Chat sessions
    # ─────────────────────────────────────────────────────────────

    def create_session(self, user_id: int, title: str = "New Chat",
                       model_name: str = None,
                       temperature: float = 0.7) -> dict | None:
        import uuid as _uuid
        now = datetime.utcnow()
        return self._execute("""
        INSERT INTO chat_sessions (
            uuid, user_id, title, model_name, temperature,
            settings, query_count, total_tokens,
            status, is_pinned, meta_data,
            created_at, updated_at, last_activity_at
        ) VALUES (
            %s, %s, %s, %s, %s,
            '{}', 0, 0,
            'active', FALSE, '{}',
            %s, %s, %s
        )
        RETURNING id, uuid, user_id, title, model_name, temperature,
                  settings, query_count, total_tokens,
                  status, is_pinned, meta_data,
                  created_at, updated_at, last_activity_at;
        """, (
            str(_uuid.uuid4()), user_id, title, model_name, temperature,
            now, now, now,
        ), fetch="one")

    def get_session_by_id(self, session_id: int) -> dict | None:
        return self._execute(
            "SELECT * FROM chat_sessions WHERE id = %s",
            (session_id,), fetch="one"
        )

    def get_session_by_uuid(self, session_uuid: str) -> dict | None:
        return self._execute(
            "SELECT * FROM chat_sessions WHERE uuid = %s",
            (session_uuid,), fetch="one"
        )

    def get_user_sessions(self, user_id: int) -> list:
        return self._execute("""
        SELECT id, uuid, user_id, title, description,
               model_name, temperature, query_count, total_tokens,
               status, is_pinned, meta_data,
               created_at, updated_at, last_activity_at
        FROM   chat_sessions
        WHERE  user_id = %s AND status != 'deleted'
        ORDER  BY is_pinned DESC, last_activity_at DESC;
        """, (user_id,), fetch="all")

    def update_session_title(self, session_id: int, title: str) -> None:
        self._execute("""
        UPDATE chat_sessions
        SET    title = %s, updated_at = %s
        WHERE  id = %s;
        """, (title, datetime.utcnow(), session_id))

    def update_session_activity(self, session_id: int) -> None:
        now = datetime.utcnow()
        self._execute("""
        UPDATE chat_sessions
        SET    last_activity_at = %s, updated_at = %s
        WHERE  id = %s;
        """, (now, now, session_id))

    def increment_query_count(self, session_id: int) -> None:
        now = datetime.utcnow()
        self._execute("""
        UPDATE chat_sessions
        SET    query_count      = query_count + 1,
               last_activity_at = %s,
               updated_at       = %s
        WHERE  id = %s;
        """, (now, now, session_id))

    def update_session_tokens(self, session_id: int, tokens: int) -> None:
        self._execute("""
        UPDATE chat_sessions
        SET    total_tokens = total_tokens + %s,
               updated_at   = %s
        WHERE  id = %s;
        """, (tokens, datetime.utcnow(), session_id))

    def archive_session(self, session_id: int) -> None:
        self._execute("""
        UPDATE chat_sessions
        SET    status = 'archived', updated_at = %s
        WHERE  id = %s;
        """, (datetime.utcnow(), session_id))

    def delete_session(self, session_id: int) -> None:
        self._execute(
            "DELETE FROM chat_sessions WHERE id = %s",
            (session_id,)
        )

    # ─────────────────────────────────────────────────────────────
    # Queries / messages
    # ─────────────────────────────────────────────────────────────

    def add_query(self, user_id: int, session_id: int, query_text: str,
                  query_type: str = "question", language: str = "en",
                  model_name: str = None,
                  temperature: float = None) -> dict | None:
        """Insert a user query row; bumps session query_count."""
        import uuid as _uuid
        now = datetime.utcnow()
        row = self._execute("""
        INSERT INTO queries (
            uuid, user_id, chat_session_id,
            query_text, query_type, language,
            model_name, temperature,
            retrieved_chunks, retrieved_documents,
            status, has_sources, meta_data,
            created_at, updated_at
        ) VALUES (
            %s, %s, %s,
            %s, %s, %s,
            %s, %s,
            '[]', '[]',
            'pending', 0, '{}',
            %s, %s
        )
        RETURNING id, uuid, user_id, chat_session_id,
                  query_text, query_type, language,
                  model_name, temperature, status,
                  created_at, updated_at;
        """, (
            str(_uuid.uuid4()), user_id, session_id,
            query_text, query_type, language,
            model_name, temperature,
            now, now,
        ), fetch="one")

        if row:
            self.increment_query_count(session_id)

        return row

    def update_query_response(self, query_id: int, response_text: str,
                               retrieved_chunks: list = None,
                               retrieved_documents: list = None,
                               retrieval_method: str = None,
                               response_time: float = None,
                               token_count: int = None,
                               relevance_score: float = None,
                               embedding_model: str = None,
                               meta_data: dict = None,
                               status: str = "completed") -> None:
        now = datetime.utcnow()
        self._execute("""
        UPDATE queries SET
            response_text       = %s,
            retrieved_chunks    = %s,
            retrieved_documents = %s,
            retrieval_method    = %s,
            response_time       = %s,
            token_count         = %s,
            relevance_score     = %s,
            embedding_model     = %s,
            meta_data           = %s,
            status              = %s,
            has_sources         = %s,
            completed_at        = %s,
            updated_at          = %s
        WHERE id = %s;
        """, (
            response_text,
            json.dumps(retrieved_chunks or []),
            json.dumps(retrieved_documents or []),
            retrieval_method,
            response_time,
            token_count,
            relevance_score,
            embedding_model,
            json.dumps(meta_data or {}),
            status,
            1 if retrieved_chunks else 0,
            now,   # completed_at
            now,   # updated_at
            query_id,
        ))

        if token_count:
            session_row = self._execute(
                "SELECT chat_session_id FROM queries WHERE id = %s",
                (query_id,), fetch="one"
            )
            if session_row and session_row.get("chat_session_id"):
                self.update_session_tokens(session_row["chat_session_id"], token_count)

    def get_session_queries(self, session_id: int) -> list:
        return self._execute("""
        SELECT id, uuid, user_id, chat_session_id,
               query_text, response_text,
               query_type, language, model_name, temperature,
               retrieved_chunks, retrieved_documents, retrieval_method,
               response_time, token_count, relevance_score,
               status, is_helpful, has_sources,
               meta_data, error_message,
               created_at, updated_at, completed_at
        FROM   queries
        WHERE  chat_session_id = %s
        ORDER  BY created_at ASC;
        """, (session_id,), fetch="all")

    def add_message(self, session_id: int, user_id: int,
                    role: str, content: str,
                    query_id: int | None = None) -> dict | None:
        """
        Convenience wrapper for the API layer.
        'user'      → new query row (status=pending).
        'assistant' → fills response on the latest pending query.
        """
        if role == "user":
            row = self.add_query(user_id, session_id, content)
            if not row:
                return None
            return {
                "id": str(row["id"]),
                "role": "user",
                "content": content,
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }

        if role == "assistant":
            if query_id is not None:
                pending = self._execute("""
                SELECT id FROM queries
                WHERE  id = %s
                  AND  chat_session_id = %s
                  AND  user_id = %s
                  AND  response_text IS NULL
                  AND  status = 'pending';
                """, (query_id, session_id, user_id), fetch="one")
            else:
                pending = self._execute("""
                SELECT id FROM queries
                WHERE  chat_session_id = %s
                  AND  response_text IS NULL
                  AND  status = 'pending'
                ORDER  BY created_at DESC
                LIMIT  1;
                """, (session_id,), fetch="one")

            if not pending:
                return None

            self.update_query_response(pending["id"], content)
            self.update_session_activity(session_id)
            return {
                "id": str(pending["id"]),
                "role": "assistant",
                "content": content,
                "created_at": datetime.utcnow().isoformat(),
            }

        return None

    def get_session_messages(self, session_id: int) -> list:
        """Flat [{role, content, ...}] list interleaving user/assistant turns."""
        rows = self.get_session_queries(session_id)
        messages = []
        for r in rows:
            messages.append({
                "id": str(r["id"]),
                "role": "user",
                "content": r["query_text"],
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            })
            if r.get("response_text"):
                messages.append({
                    "id": str(r["id"]),
                    "role": "assistant",
                    "content": r["response_text"],
                    "is_helpful": r.get("is_helpful"),
                    "meta_data": r.get("meta_data", {}),
                    "created_at": r["completed_at"].isoformat() if r.get("completed_at") else None,
                })
        return messages

    # ─────────────────────────────────────────────────────────────
    # Feedback: like/dislike + user comment
    # ─────────────────────────────────────────────────────────────

    def update_query_feedback(self, query_id: int, is_helpful: int) -> dict | None:
        """Set is_helpful: 1 = like, 0 = dislike, None = reset."""
        now = datetime.utcnow()
        return self._execute("""
        UPDATE queries
        SET    is_helpful = %s, updated_at = %s
        WHERE  id = %s
        RETURNING id, is_helpful;
        """, (is_helpful, now, query_id), fetch="one")

    def update_query_comment(self, query_id: int, comment: str) -> dict | None:
        """Store user comment inside the meta_data JSON column."""
        now = datetime.utcnow()

        # First, fetch the current meta_data
        row = self._execute(
            "SELECT meta_data FROM queries WHERE id = %s",
            (query_id,), fetch="one"
        )
        if not row:
            return None

        meta = row.get("meta_data") or {}
        if isinstance(meta, str):
            meta = json.loads(meta)

        meta["user_comment"] = comment

        return self._execute("""
                             UPDATE queries
                             SET meta_data = %s::json,
               updated_at = %s
                             WHERE id = %s
                                 RETURNING id
                                 , meta_data;
                             """, (json.dumps(meta, ensure_ascii=False), now, query_id), fetch="one")


    # ─────────────────────────────────────────────────────────────
        # CHUNKS AND DOC INFO: get chunk documents
    # ─────────────────────────────────────────────────────────────
    def get_chunks_by_id(self, chunk_id: int) -> list[str]:
        """Return all chunks belonging to the given id."""
        return self._execute("SELECT content FROM chunks WHERE id = %s",
            (chunk_id,), fetch="all")

    def get_number_of_chunks(self) -> list[str]:
        """Return all chunks belonging to the given id."""
        return self._execute("SELECT COUNT(*) FROM chunks", fetch="all")

    def get_available_documents(self):
        """Return only named documents that have retrievable chunks."""
        return self._execute("""
            SELECT DISTINCT d.title
            FROM documents d
            WHERE NULLIF(BTRIM(d.title), '') IS NOT NULL
              AND EXISTS (
                  SELECT 1
                  FROM chunks c
                  WHERE c.document_id = d.id
              )
            ORDER BY d.title
        """, fetch="all")

    def filter_available_document_titles(self, titles: list[str]) -> list[str]:
        """Discard blank, duplicate, or stale client-supplied datasource names."""
        requested = list(dict.fromkeys(
            str(title).strip() for title in titles if str(title).strip()
        ))
        if not requested:
            return []
        rows = self._execute("""
            SELECT DISTINCT d.title
            FROM documents d
            WHERE d.title = ANY (%s)
              AND NULLIF(BTRIM(d.title), '') IS NOT NULL
              AND EXISTS (
                  SELECT 1
                  FROM chunks c
                  WHERE c.document_id = d.id
              )
        """, (requested,), fetch="all")
        existing = {row["title"] for row in rows}
        return [title for title in requested if title in existing]

    def get_chunks_by_document_titles(self, titles: list[str]) -> list[dict]:
        """Return all chunks (id, content, document title) for the given document titles."""
        return self._execute("""
                             SELECT c.id AS chunk_id, c.content AS text, d.title AS document_name
                             FROM chunks c
                                      JOIN documents d ON c.document_id = d.id
                             WHERE d.title = ANY (%s)
                             """, (titles,), fetch="all")

    def get_chunks_revision_by_document_titles(self, titles: list[str]) -> str:
        """Return the transactional cross-process revision for a corpus."""
        rows = self._execute("""
            SELECT COALESCE(
                STRING_AGG(
                    d.id::text || ':' || COALESCE(r.revision, 0)::text,
                    ',' ORDER BY d.id
                ),
                ''
            ) AS revision
            FROM documents d
            LEFT JOIN knowledge_document_revisions r ON r.document_id = d.id
            WHERE d.title = ANY (%s)
        """, (titles,), fetch="one")
        if not rows:
            return ""
        return str(rows.get("revision") or "")


    @staticmethod
    def _db_history_to_api_format(db_messages):
        pairs = []
        current = {}
        for m in db_messages:
            if m["role"] == "user":
                current = {"user": m["content"]}
            elif m["role"] == "assistant":
                current["ai"] = m["content"]
                pairs.append(current)
                current = {}
        return pairs

    def toggle_session_pin(self, session_id: int) -> None:
        """Toggle the is_pinned flag for a chat session."""
        self._execute("""
                      UPDATE chat_sessions
                      SET is_pinned  = NOT is_pinned,
                          updated_at = %s
                      WHERE id = %s
                      """, (datetime.utcnow(), session_id))


    def get_session_metadata(self, session_id: int) -> dict:
        """Return the meta_data JSON column for a session."""
        row = self._execute(
            "SELECT meta_data FROM chat_sessions WHERE id = %s",
            (session_id,), fetch="one"
        )
        if not row or not row.get("meta_data"):
            return {}
        meta = row["meta_data"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        return meta

    def update_session_metadata(self, session_id: int, metadata: dict) -> None:
        """Overwrite the meta_data JSON column."""
        now = datetime.utcnow()
        self._execute(
            "UPDATE chat_sessions SET meta_data = %s, updated_at = %s WHERE id = %s",
            (json.dumps(metadata, ensure_ascii=False), now, session_id)
        )

    def get_or_create_mobile_session(self, user_id: int, session_uuid: str) -> dict:
        """Resolves a mobile string UUID to an internal session, creating it if missing."""
        existing = self.get_session_by_uuid(session_uuid)
        if existing:
            return existing

        # Create new session mapping to the mobile app's specific UUID
        now = datetime.utcnow()
        return self._execute("""
                             INSERT INTO chat_sessions (uuid, user_id, title, model_name, temperature,
                                                        settings, query_count, total_tokens,
                                                        status, is_pinned, meta_data,
                                                        created_at, updated_at, last_activity_at)
                             VALUES (%s, %s, %s, NULL, 0.7,
                                     '{}', 0, 0,
                                     'active', FALSE, '{}',
                                     %s, %s, %s) RETURNING *;
                             """, (session_uuid, user_id, "Mobile App Chat", now, now, now), fetch="one")
# ==================== CHAT MANAGER ====================

class ChatManager:
    """
    High-level interface over DatabaseManager.
    Session IDs exposed to the API are integer PKs cast to str.
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    # ── Sessions ───────────────────────────────────────────────

    def create_new_chat(self, user_id: int, title: str = "New Chat",
                        model_name: str = None,
                        temperature: float = 0.7) -> dict:
        row = self.db.create_session(user_id, title, model_name, temperature)
        if not row:
            raise RuntimeError("Failed to create chat session")
        return self._format_session(row)

    def get_user_sessions(self, user_id: int) -> dict:
        """Returns {session_id_str: session_dict} mapping."""
        rows = self.db.get_user_sessions(user_id)
        return {str(r["id"]): self._format_session(r) for r in rows}

    def get_session(self, session_id: str) -> dict | None:
        row = self.db.get_session_by_id(int(session_id))
        if not row:
            return None
        result = self._format_session(row)
        result["messages"] = self.db.get_session_messages(int(session_id))
        return result

    def update_title(self, session_id: str, title: str) -> str:
        short = title[:40] + "..." if len(title) > 40 else title
        self.db.update_session_title(int(session_id), short)
        return short

    def delete_chat(self, session_id: str) -> None:
        self.db.delete_session(int(session_id))

    def switch_chat(self, chat_id: str) -> list:
        messages = self.db.get_session_messages(chat_id)
        return messages if messages else []  # Ensure it returns an empty list, not None

    # ── Messages ───────────────────────────────────────────────

    def add_message(self, session_id: str, role: str, content: str,
                    user_id: int = None,
                    query_id: int | None = None) -> dict | None:

        # print("*"*10)
        # print("adding message")

        if user_id is None:
            row = self.db.get_session_by_id(int(session_id))
            if not row:
                return None
            user_id = row["user_id"]

        msg = self.db.add_message(
            int(session_id), user_id, role, content, query_id=query_id
        )

        # Auto-title from the first user message
        if role == "user" and msg:
            session_row = self.db.get_session_by_id(int(session_id))
            if session_row and session_row.get("title") in (None, "New Chat"):
                self.update_title(session_id, content)

        return msg

    def get_messages(self, session_id: str) -> list:

        # print("//"*50)
        # print("session_id", session_id)
        # print("//"*50)

        return self.db.get_session_messages(int(session_id))

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _format_session(row: dict) -> dict:
        def _iso(val):
            if val is None:
                return None
            return val.isoformat() if isinstance(val, datetime) else str(val)

        return {
            "id":               str(row["id"]),
            "uuid":             row.get("uuid"),
            "title":            row.get("title") or "New Chat",
            "description":      row.get("description"),
            "model_name":       row.get("model_name"),
            "temperature":      row.get("temperature", 0.7),
            "query_count":      row.get("query_count", 0),
            "total_tokens":     row.get("total_tokens", 0),
            "status":           row.get("status", "active"),
            "is_pinned":        row.get("is_pinned", False),
            "meta_data":        row.get("meta_data", {}),
            "created_at":       _iso(row.get("created_at")),
            "updated_at":       _iso(row.get("updated_at")),
            "last_activity_at": _iso(row.get("last_activity_at")),
        }

    def toggle_pin(self, session_id: str) -> dict:
        """Toggle pin status and return updated session."""
        self.db.toggle_session_pin(int(session_id))
        row = self.db.get_session_by_id(int(session_id))
        if not row:
            raise RuntimeError("Session not found after pin toggle")
        return self._format_session(row)

    def resolve_mobile_session(self, user_id: int, session_uuid: str) -> str:
        """Returns the internal integer ID (as a string) based on the mobile UUID."""
        if not session_uuid:
            raise ValueError("Mobile sessionID cannot be empty")

        row = self.db.get_or_create_mobile_session(user_id, session_uuid)
        return str(row["id"])
