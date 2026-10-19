from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from dotenv import dotenv_values

from coverage_check.settings import DEFAULT_ARTIFACT_DIR
from scripts.check_tracked_secrets import secret_key
from scripts.validate_environment import SPECS, analyze_environment, render_text


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
        "INTENT_CLASSIFIER_MODEL_PATH=synthetic-checkpoint.pt",
        "INTENT_CLASSIFIER_THRESHOLD=0.875",
        "INTENT_CLASSIFIER_DEVICE=cpu",
        "INTENT_CLASSIFIER_REQUIRED=false",
        "INTENT_CLASSIFIER_EXPECTED_SHA256=" + "a" * 64,
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


# The keys coverage_check/settings.py reads, with the code's default and range.
_COVERAGE_READ = re.compile(
    r'_(int|bool)\(env, "(KNOWLEDGE_COVERAGE_[A-Z_]+)", "?([^",)]+)"?(?:, ([^,)]+), ([^,)]+))?\)'
)
OLD_AUDIT_KEYS = {
    "KNOWLEDGE_COVERAGE_" + name for name in (
        "TOKEN_MARGIN", "BATCH_MAX_ENTRIES", "MAX_RUN_ROWS", "MAX_COMPLETIONS", "MAX_TOKENS",
        "MAX_EXECUTION_SECONDS", "MAX_CONSECUTIVE_FAILURES", "MIN_FREE_BYTES", "PACE_MS",
        "RETENTION_DAYS", "INITIAL_DEPTH", "INITIAL_ENTRIES", "MAX_ENTRY_BUDGET",
        "VERIFICATION_PASSES", "DEDUPE", "REQUIRE_SECOND_REVIEWER", "PUBLIC_CONTACTS",
    )
} | {"KNOWLEDGE_RECOMMENDATION_MAX_COMPLETIONS"}


def coverage_settings_keys() -> dict[str, tuple[str, str, str | None, str | None]]:
    source = (REPOSITORY_ROOT / "coverage_check" / "settings.py").read_text(encoding="utf-8")
    keys = {key: (kind, default, low, high) for kind, key, default, low, high in _COVERAGE_READ.findall(source)}
    keys["KNOWLEDGE_COVERAGE_ARTIFACT_DIR"] = ("path", DEFAULT_ARTIFACT_DIR, None, None)
    return keys


class CoverageSettingsContractTests(unittest.TestCase):
    def test_every_coverage_key_has_a_spec_with_the_code_default_and_range(self):
        keys = coverage_settings_keys()
        self.assertEqual(len(keys), 15)
        self.assertIn("KNOWLEDGE_COVERAGE_SUGGEST_CONTEXT", keys)
        self.assertIn("KNOWLEDGE_COVERAGE_SUGGEST_MAX_TOKENS", keys)
        for key, (kind, default, low, high) in keys.items():
            spec = SPECS[key]
            self.assertEqual((spec.kind, spec.default), (kind, default), key)
            # KEEP and BROADER_DEPTH are bounded by DEPTH; the validator cross-checks those.
            if low and low.isdigit():
                self.assertEqual(spec.minimum, int(low), key)
            if high and high.isdigit():
                self.assertEqual(spec.maximum, int(high), key)

    def test_old_audit_keys_are_gone_and_reported_as_unknown(self):
        self.assertFalse(OLD_AUDIT_KEYS & set(SPECS))
        for name in ("env.example", "env.review.example", "Production_ENV.example", ".env.example.generated"):
            self.assertFalse(OLD_AUDIT_KEYS & set(dotenv_values(REPOSITORY_ROOT / name, interpolate=False)), name)
        report = EnvironmentValidatorTests.analyze(
            None, minimum_environment() + "KNOWLEDGE_COVERAGE_TOKEN_MARGIN=128\n"
        )
        unknown = [item for item in report["findings"] if item["variable"] == "KNOWLEDGE_COVERAGE_TOKEN_MARGIN"]
        self.assertEqual([item["severity"] for item in unknown], ["warning"])

    def test_templates_list_every_coverage_key_with_its_code_default(self):
        keys = coverage_settings_keys()
        production = {
            key: value
            for key, value in dotenv_values(REPOSITORY_ROOT / "Production_ENV.example", interpolate=False).items()
            if key.startswith("KNOWLEDGE_COVERAGE_")
        }
        self.assertEqual(production, {key: default for key, (_, default, _, _) in keys.items()})
        for name in ("env.example", ".env.example.generated"):
            values = dotenv_values(REPOSITORY_ROOT / name, interpolate=False)
            for key, (_, default, _, _) in keys.items():
                self.assertEqual(values.get(key), default, (name, key))

    def test_production_example_has_empty_secrets_and_local_files_stay_ignored(self):
        values = dotenv_values(REPOSITORY_ROOT / "Production_ENV.example", interpolate=False)
        self.assertTrue(all(value == "" for key, value in values.items() if secret_key(key)))
        if (REPOSITORY_ROOT / "Production_ENV").exists():
            self.assertEqual(set(dotenv_values(REPOSITORY_ROOT / "Production_ENV", interpolate=False)), set(values))
        ignore = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("/.env", ignore)
        self.assertIn("/Production_ENV", ignore)

    def test_review_examples_keep_database_user_placeholders(self):
        for name in ("env.example", "env.review.example"):
            text = (REPOSITORY_ROOT / name).read_text(encoding="utf-8")
            self.assertIn("POSTGRES_USER=CHANGE_ME_POSTGRES_USER", text, name)
            self.assertIn("DEFAULT_DB_USER=CHANGE_ME_POSTGRES_USER", text, name)

    def test_coverage_flag_is_validated_in_production(self):
        for value, rejected in (("true", False), ("false", False), ("1", True), ("maybe", True)):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "synthetic.env"
                path.write_text(f"KNOWLEDGE_COVERAGE_ENABLED={value}\nENVIRONMENT=production\n", encoding="utf-8")
                report = analyze_environment(path, "production", process_environment={})
            critical = any(item["variable"] == "KNOWLEDGE_COVERAGE_ENABLED" and item["severity"] == "critical"
                           for item in report["findings"])
            self.assertIs(critical, rejected, value)

    def test_suggestion_settings_are_range_checked(self):
        for key, bad, good in (("KNOWLEDGE_COVERAGE_SUGGEST_CONTEXT", "21", "20"),
                               ("KNOWLEDGE_COVERAGE_SUGGEST_MAX_TOKENS", "127", "128")):
            for value, rejected in ((bad, True), (good, False)):
                report = EnvironmentValidatorTests.analyze(None, minimum_environment() + f"{key}={value}\n")
                critical = any(item["variable"] == key and item["severity"] == "critical"
                               for item in report["findings"])
                self.assertIs(critical, rejected, (key, value))


if __name__ == "__main__":
    unittest.main()
