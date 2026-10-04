"""Startup dependency diagnostics must obey the JSON stdout contract."""

import io
import json
import logging
import unittest
from contextlib import redirect_stdout
from unittest import mock

from new_architecture.app.services.db_connection import connection
from utils.structured_logging import LoggingSettings, start_logging


class StartupStdoutTests(unittest.TestCase):
    def test_connection_failure_uses_safe_structured_event(self):
        stream = io.StringIO()
        plaintext = io.StringIO()
        runtime = start_logging(LoggingSettings(environment="test"), stream)
        try:
            with mock.patch.object(connection.psycopg2, "connect", side_effect=RuntimeError("SYNTHETIC-CONNECTION-SECRET")):
                with redirect_stdout(plaintext):
                    result = connection.DatabaseConnections().connect_all()
        finally:
            runtime.close()

        self.assertFalse(result)
        self.assertEqual(plaintext.getvalue(), "")
        lines = stream.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        event = json.loads(lines[0])
        self.assertEqual(event["event"], "dependency_connect_failed")
        self.assertEqual(event["data"], {"dependency": "postgres", "error": {"type": "RuntimeError"}})
        self.assertNotIn("SYNTHETIC-CONNECTION-SECRET", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
