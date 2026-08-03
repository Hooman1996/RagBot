import os
import unittest
from unittest.mock import MagicMock, patch

import kb_manager


class KnowledgeBaseDatabaseConfigTests(unittest.TestCase):
    database_environment = {
        "POSTGRES_HOST": "database.internal",
        "POSTGRES_PORT": "6543",
        "POSTGRES_DB": "knowledge",
        "POSTGRES_USER": "knowledge-user",
        "POSTGRES_PASSWORD": "synthetic-password",
    }

    def test_connection_uses_application_postgres_environment(self):
        connection = MagicMock()

        with (
            patch.dict(os.environ, self.database_environment, clear=True),
            patch.object(
                kb_manager.psycopg2,
                "connect",
                return_value=connection,
            ) as connect,
        ):
            result = kb_manager.get_db_connection()

        self.assertIs(result, connection)
        connect.assert_called_once_with(
            host="database.internal",
            port="6543",
            dbname="knowledge",
            user="knowledge-user",
            password="synthetic-password",
            cursor_factory=kb_manager.psycopg2.extras.RealDictCursor,
        )
        connection.commit.assert_called_once_with()

    def test_missing_database_configuration_fails_before_connecting(self):
        incomplete_environment = self.database_environment | {
            "POSTGRES_PASSWORD": ""
        }

        with (
            patch.dict(os.environ, incomplete_environment, clear=True),
            patch.object(kb_manager.psycopg2, "connect") as connect,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "POSTGRES_PASSWORD",
            ):
                kb_manager.get_db_connection()

        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
