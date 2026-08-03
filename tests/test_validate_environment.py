from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.validate_environment import analyze_environment, render_text


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPOSITORY_ROOT / "scripts" / "validate_environment.py"


def minimum_environment(*, production: bool = False) -> str:
    lines = [
        "POSTGRES_HOST=localhost",
        "POSTGRES_PORT=5432",
        "POSTGRES_DB=ragbot",
        "POSTGRES_USER=synthetic-user",
        "POSTGRES_PASSWORD=synthetic-password",
        "MINIO_ACCESS_KEY=synthetic-access",
        "MINIO_SECRET_KEY=synthetic-secret",
        "MINIO_BUCKET=documents",
        "TEI_EMBED_URL=http://127.0.0.1:7997",
        "TEI_RERANK_URL=http://127.0.0.1:7998",
    ]
    if production:
        lines.append("QDRANT_API_KEY=synthetic-qdrant-key")
    return "\n".join(lines) + "\n"


class EnvironmentValidatorTests(unittest.TestCase):
    def analyze(self, content: str, mode: str = "staging"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.synthetic"
            path.write_text(content, encoding="utf-8")
            return analyze_environment(
                path,
                mode,
                show_optional=True,
                process_environment={},
            )

    def finding_variables(self, report, severity: str | None = None):
        return {
            item["variable"]
            for item in report["findings"]
            if severity is None or item["severity"] == severity
        }

    def test_secret_values_never_appear_in_text_or_json_output(self):
        sentinel = "DO-NOT-LEAK-SECRET-7f1c"
        report = self.analyze(
            minimum_environment().replace(
                "synthetic-password", sentinel
            )
            + f"RAGBOT_STAGING_AUTH_TOKEN={sentinel}\n"
        )
        text = render_text(report)
        serialized = json.dumps(report)
        self.assertNotIn(sentinel, text)
        self.assertNotIn(sentinel, serialized)

    def test_required_missing_variable_is_critical(self):
        report = self.analyze(
            minimum_environment().replace("POSTGRES_PASSWORD=synthetic-password\n", "")
        )
        self.assertIn("POSTGRES_PASSWORD", self.finding_variables(report, "critical"))
        self.assertGreater(report["summary"]["critical"], 0)

    def test_malformed_integer(self):
        report = self.analyze(minimum_environment() + "API_PORT=eighty\n")
        self.assertIn("API_PORT", self.finding_variables(report, "critical"))

    def test_malformed_float(self):
        report = self.analyze(
            minimum_environment()
            + "APPLICATION_REQUEST_TIMEOUT_SECONDS=soon\n"
        )
        self.assertIn(
            "APPLICATION_REQUEST_TIMEOUT_SECONDS",
            self.finding_variables(report, "critical"),
        )

    def test_malformed_boolean(self):
        report = self.analyze(minimum_environment() + "QDRANT_HTTPS=perhaps\n")
        self.assertIn("QDRANT_HTTPS", self.finding_variables(report, "critical"))

    def test_malformed_url(self):
        report = self.analyze(
            minimum_environment().replace(
                "TEI_EMBED_URL=http://127.0.0.1:7997",
                "TEI_EMBED_URL=127.0.0.1:7997",
            )
        )
        self.assertIn("TEI_EMBED_URL", self.finding_variables(report, "critical"))

    def test_unknown_variable(self):
        report = self.analyze(minimum_environment() + "NOT_A_RAGBOT_SETTING=1\n")
        self.assertIn(
            "NOT_A_RAGBOT_SETTING", self.finding_variables(report, "warning")
        )

    def test_deprecated_variable(self):
        report = self.analyze(
            minimum_environment() + "QDRANT_URL=http://127.0.0.1:6333\n"
        )
        self.assertIn("QDRANT_URL", self.finding_variables(report, "warning"))

    def test_overlapping_variables(self):
        report = self.analyze(
            minimum_environment()
            + "QDRANT_URL=http://127.0.0.1:6333\nQDRANT_HOST=localhost\n"
        )
        groups = {item["group"] for item in report["overlaps"]}
        self.assertIn("qdrant address", groups)

    def test_staging_and_production_requirements_differ(self):
        staging = self.analyze(minimum_environment(), mode="staging")
        production = self.analyze(minimum_environment(), mode="production")
        self.assertNotIn(
            "QDRANT_API_KEY", self.finding_variables(staging, "critical")
        )
        self.assertIn(
            "QDRANT_API_KEY", self.finding_variables(production, "critical")
        )

    def test_json_output_is_valid_and_omits_values(self):
        sentinel = "JSON-SECRET-SENTINEL"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.synthetic"
            path.write_text(
                minimum_environment().replace("synthetic-password", sentinel),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--env-file",
                    str(path),
                    "--mode",
                    "staging",
                    "--format",
                    "json",
                ],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                check=False,
                env={},
            )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["mode"], "staging")
        self.assertNotIn(sentinel, completed.stdout)

    def test_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / "valid.env"
            invalid = Path(directory) / "invalid.env"
            valid.write_text(minimum_environment(), encoding="utf-8")
            invalid.write_text("API_PORT=bad\n", encoding="utf-8")
            valid_run = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--env-file",
                    str(valid),
                    "--mode",
                    "staging",
                ],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                check=False,
                env={},
            )
            invalid_run = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--env-file",
                    str(invalid),
                    "--mode",
                    "staging",
                ],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                check=False,
                env={},
            )
        self.assertEqual(valid_run.returncode, 0)
        self.assertNotEqual(invalid_run.returncode, 0)


if __name__ == "__main__":
    unittest.main()
