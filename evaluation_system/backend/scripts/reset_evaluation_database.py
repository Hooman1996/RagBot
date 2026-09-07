"""Explicitly delete only the isolated PostgreSQL evaluation schema."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from typing import Any, TextIO

from evaluation_system.backend.app.config import get_settings


EVALUATION_SCHEMA = "evaluation"
CONFIRMATION = "DROP_EVALUATION_SCHEMA"
DROP_SCHEMA_SQL = "DROP SCHEMA IF EXISTS evaluation CASCADE"


def build_parser() -> argparse.ArgumentParser:
    description = (
        "This utility permanently deletes only the PostgreSQL `evaluation` "
        "schema and its evaluation data. It does not recreate the schema. "
        "After reset, use the Evaluation System panel's Initialize Database "
        "action."
    )
    examples = """examples:
  python3 -m evaluation_system.backend.scripts.reset_evaluation_database \\
    --confirm DROP_EVALUATION_SCHEMA

  bash evaluation_system/backend/scripts/reset_evaluation_database.sh \\
    --confirm DROP_EVALUATION_SCHEMA
"""
    parser = argparse.ArgumentParser(
        description=description,
        epilog=examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--confirm",
        metavar=CONFIRMATION,
        help=f"required exact confirmation phrase: {CONFIRMATION}",
    )
    return parser


def _print_target(settings: Any, output: TextIO) -> None:
    print(f"Database host : {settings.postgres_host or '(default)'}", file=output)
    print(f"Database port : {settings.postgres_port}", file=output)
    print(f"Database name : {settings.postgres_db}", file=output)
    print(f"Database user : {settings.postgres_user}", file=output)
    print(f"Schema        : {EVALUATION_SCHEMA}", file=output)
    print(file=output)
    print(
        "This will permanently delete ONLY the PostgreSQL schema `evaluation` "
        "and all evaluation datasets/runs/results stored inside it.",
        file=output,
    )


def reset_evaluation_schema(
    settings: Any,
    *,
    engine_factory: Callable[..., Any] | None = None,
    inspector_factory: Callable[[Any], Any] | None = None,
    text_factory: Callable[[str], Any] | None = None,
) -> bool:
    """Drop the fixed evaluation schema and return whether it is absent."""

    if engine_factory is None or inspector_factory is None or text_factory is None:
        from sqlalchemy import create_engine, inspect, text

        engine_factory = engine_factory or create_engine
        inspector_factory = inspector_factory or inspect
        text_factory = text_factory or text

    engine = engine_factory(
        settings.sqlalchemy_url(async_driver=False),
        pool_pre_ping=True,
        hide_parameters=True,
    )
    try:
        with engine.begin() as connection:
            connection.execute(text_factory(DROP_SCHEMA_SQL))
        with engine.connect() as connection:
            return not inspector_factory(connection).has_schema(EVALUATION_SCHEMA)
    finally:
        engine.dispose()


def main(
    argv: Sequence[str] | None = None,
    *,
    settings_factory: Callable[[], Any] = get_settings,
    engine_factory: Callable[..., Any] | None = None,
    inspector_factory: Callable[[Any], Any] | None = None,
    text_factory: Callable[[str], Any] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output = stdout or sys.stdout
    errors = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.confirm != CONFIRMATION:
        print(f"Refusing reset: --confirm must equal {CONFIRMATION}.", file=errors)
        parser.print_usage(errors)
        return 2

    try:
        settings = settings_factory()
        _print_target(settings, output)
        schema_is_absent = reset_evaluation_schema(
            settings,
            engine_factory=engine_factory,
            inspector_factory=inspector_factory,
            text_factory=text_factory,
        )
    except Exception as exc:
        print(
            f"Evaluation schema reset failed ({type(exc).__name__}).",
            file=errors,
        )
        return 1

    if not schema_is_absent:
        print("Evaluation schema reset failed: schema still exists.", file=errors)
        return 1

    print("Evaluation schema reset successfully.", file=output)
    print("Database status should now be NOT_INITIALIZED.", file=output)
    print(
        "Open the Evaluation System panel and click Initialize Database.",
        file=output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
