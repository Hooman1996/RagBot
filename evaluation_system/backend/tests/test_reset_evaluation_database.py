from __future__ import annotations

import io
import re
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace

from evaluation_system.backend.scripts import reset_evaluation_database as reset


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "evaluation_system/backend/scripts/reset_evaluation_database.py"
WRAPPER = ROOT / "evaluation_system/backend/scripts/reset_evaluation_database.sh"


class Context:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args):
        return False


class Connection:
    def __init__(self, statements, error=None):
        self.statements = statements
        self.error = error

    def execute(self, statement):
        if self.error is not None:
            raise self.error
        self.statements.append(str(statement))


class Engine:
    def __init__(self, *, schema_exists=False, error=None):
        self.statements = []
        self.schema_exists = schema_exists
        self.error = error
        self.disposed = False

    def begin(self):
        return Context(Connection(self.statements, self.error))

    def connect(self):
        return Context(Connection(self.statements))

    def dispose(self):
        self.disposed = True


class ResetEvaluationDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.password = "super-secret-password"
        self.full_url = f"postgresql://ragbot:{self.password}@db.internal:5432/ragbot"
        self.url_calls = []

        def sqlalchemy_url(**kwargs):
            self.url_calls.append(kwargs)
            return self.full_url

        self.settings = SimpleNamespace(
            postgres_host="db.internal",
            postgres_port=5432,
            postgres_db="ragbot",
            postgres_user="ragbot",
            postgres_password=self.password,
            sqlalchemy_url=sqlalchemy_url,
        )

    def invoke(self, argv, engine):
        output = io.StringIO()
        errors = io.StringIO()
        engine_calls = []

        def engine_factory(*args, **kwargs):
            engine_calls.append((args, kwargs))
            return engine

        code = reset.main(
            argv,
            settings_factory=lambda: self.settings,
            engine_factory=engine_factory,
            inspector_factory=lambda _connection: SimpleNamespace(
                has_schema=lambda schema: engine.schema_exists
                if schema == reset.EVALUATION_SCHEMA
                else True
            ),
            text_factory=lambda statement: statement,
            stdout=output,
            stderr=errors,
        )
        return code, output.getvalue(), errors.getvalue(), engine_calls

    def test_missing_confirmation_does_not_create_engine(self):
        engine = Engine()
        code, _output, errors, calls = self.invoke([], engine)
        self.assertNotEqual(code, 0)
        self.assertIn("usage:", errors)
        self.assertEqual(calls, [])
        self.assertEqual(engine.statements, [])

    def test_wrong_confirmation_does_not_execute_drop(self):
        engine = Engine()
        code, _output, _errors, calls = self.invoke(
            ["--confirm", "wrong"], engine
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(calls, [])
        self.assertEqual(engine.statements, [])

    def test_correct_confirmation_executes_exactly_one_destructive_statement(self):
        engine = Engine(schema_exists=False)
        code, output, errors, calls = self.invoke(
            ["--confirm", reset.CONFIRMATION], engine
        )
        self.assertEqual(code, 0)
        self.assertEqual(errors, "")
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.url_calls, [{"async_driver": False}])
        self.assertEqual(calls[0][0], (self.full_url,))
        self.assertTrue(calls[0][1]["hide_parameters"])
        self.assertEqual(engine.statements, [reset.DROP_SCHEMA_SQL])
        self.assertEqual(
            " ".join(engine.statements[0].upper().split()),
            "DROP SCHEMA IF EXISTS EVALUATION CASCADE",
        )
        self.assertIn("NOT_INITIALIZED", output)
        self.assertTrue(engine.disposed)

    def test_no_arbitrary_schema_argument_exists(self):
        option_destinations = {action.dest for action in reset.build_parser()._actions}
        self.assertEqual(option_destinations, {"help", "confirm"})
        engine = Engine()
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                self.invoke(["--schema", "public"], engine)
        self.assertNotEqual(caught.exception.code, 0)
        self.assertEqual(engine.statements, [])

    def test_target_summary_never_prints_password_or_full_url(self):
        code, output, errors, _calls = self.invoke(
            ["--confirm", reset.CONFIRMATION], Engine(schema_exists=False)
        )
        self.assertEqual(code, 0)
        rendered = output + errors
        self.assertNotIn(self.password, rendered)
        self.assertNotIn(self.full_url, rendered)
        self.assertIn("Schema        : evaluation", output)

    def test_schema_still_existing_returns_nonzero(self):
        code, _output, errors, _calls = self.invoke(
            ["--confirm", reset.CONFIRMATION], Engine(schema_exists=True)
        )
        self.assertNotEqual(code, 0)
        self.assertIn("schema still exists", errors)

    def test_database_exception_is_nonzero_and_does_not_leak_credentials(self):
        engine = Engine(error=RuntimeError(self.full_url))
        code, output, errors, _calls = self.invoke(
            ["--confirm", reset.CONFIRMATION], engine
        )
        self.assertNotEqual(code, 0)
        self.assertNotIn(self.password, output + errors)
        self.assertNotIn(self.full_url, output + errors)
        self.assertIn("RuntimeError", errors)
        self.assertTrue(engine.disposed)

    def test_help_documents_both_exact_commands_and_no_recreation(self):
        help_text = reset.build_parser().format_help()
        self.assertIn("--confirm DROP_EVALUATION_SCHEMA", help_text)
        self.assertIn("reset_evaluation_database.sh", help_text)
        self.assertIn("does not recreate the schema", help_text)
        self.assertIn("Initialize Database", help_text)

    def test_shell_wrapper_passes_arguments_through(self):
        source = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", source)
        self.assertIn(
            'exec python3 -m evaluation_system.backend.scripts.'
            'reset_evaluation_database "$@"',
            source,
        )

    def test_source_allows_only_the_fixed_destructive_statement(self):
        source = SCRIPT.read_text(encoding="utf-8")
        destructive_sql = re.findall(
            r'(?im)^\s*[A-Z_]+\s*=\s*"((?:DROP|TRUNCATE|DELETE) [^"]+)"',
            source,
        )
        self.assertEqual(destructive_sql, [reset.DROP_SCHEMA_SQL])
        upper_source = source.upper()
        for forbidden in (
            "DROP SCHEMA PUBLIC",
            "DROP DATABASE",
            "TRUNCATE ",
            "DELETE FROM",
            "DROP OWNED",
            "REASSIGN OWNED",
        ):
            self.assertNotIn(forbidden, upper_source)


if __name__ == "__main__":
    unittest.main()
