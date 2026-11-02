"""Coverage storage schema shared by startup and the owner command."""

TABLES = ("coverage_runs", "coverage_rows", "coverage_chunks")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS coverage_runs (
    run_id          VARCHAR(34)  PRIMARY KEY,
    owner_id        INTEGER      NOT NULL,
    created_at      TIMESTAMPTZ  NOT NULL,
    file_name       TEXT         NOT NULL,
    documents       JSONB        NOT NULL,
    settings        JSONB        NOT NULL,
    prompt_version  TEXT         NOT NULL,
    state           VARCHAR(16)  NOT NULL,
    row_count       INTEGER      NOT NULL
);
CREATE INDEX IF NOT EXISTS coverage_runs_created_at_idx ON coverage_runs (created_at DESC, run_id DESC);

CREATE TABLE IF NOT EXISTS coverage_rows (
    run_id             VARCHAR(34) NOT NULL REFERENCES coverage_runs(run_id) ON DELETE CASCADE,
    row_number         INTEGER     NOT NULL,
    input              JSONB       NOT NULL,
    result_code        VARCHAR(32),
    result             JSONB,
    suggestion_status  VARCHAR(16),
    suggestion         JSONB,
    PRIMARY KEY (run_id, row_number)
);

CREATE TABLE IF NOT EXISTS coverage_chunks (
    run_id    VARCHAR(34) NOT NULL REFERENCES coverage_runs(run_id) ON DELETE CASCADE,
    text_key  CHAR(64)    NOT NULL,
    text      TEXT        NOT NULL,
    PRIMARY KEY (run_id, text_key)
);
"""
