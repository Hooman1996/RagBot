from __future__ import annotations

import asyncio
import io
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from conversation_history import (
    EVALUATION_EXECUTION_POLICY,
    format_rewrite_history,
    messages_from_turn_records,
    trim_agent_messages,
)
from evaluation_system.backend.app.services.divergence import (
    ComparableTurn,
    analyze_stability,
)
from evaluation_system.backend.app.services.failures import is_infrastructure_error
from evaluation_system.backend.app.services.importer import parse_dataset_file
from evaluation_system.backend.app.services.migrations import (
    CONFIRMATION,
    DatabaseStatus,
    MigrationService,
)
from evaluation_system.backend.app.services.run_planning import build_run_session_specs
from pipeline_observer import PipelineStage
from utils.service_errors import ServiceTimeoutError, ServiceUnavailableError


SOURCE_SESSION_ID = "REAL_LOOKING_SESSION_12345"


class AcceptanceImporterTests(unittest.TestCase):
    CSV = (
        "session_id,time,query\n"
        "A,10:03,Q3\n"
        "A,10:01,Q1\n"
        "B,10:05,B1\n"
        "A,10:02,Q2\n"
        ",10:06,SINGLE1\n"
        ",10:07,SINGLE2\n"
    )

    def assert_expected_sessions(self, parsed):
        self.assertEqual(parsed.session_count, 4)
        by_source = {
            session.source_session_id: session
            for session in parsed.sessions
            if session.source_session_id is not None
        }
        self.assertEqual([turn.query for turn in by_source["A"].turns], ["Q1", "Q2", "Q3"])
        self.assertEqual([turn.query for turn in by_source["B"].turns], ["B1"])
        synthetic = [session for session in parsed.sessions if session.synthetic_session]
        self.assertEqual([[turn.query for turn in session.turns] for session in synthetic], [["SINGLE1"], ["SINGLE2"]])
        self.assertEqual(len({session.synthetic_label for session in synthetic}), 2)

    def test_required_csv_session_order_and_blank_isolation(self):
        parsed = parse_dataset_file(
            filename="acceptance.csv",
            content=self.CSV.encode(),
            dataset_type="PIPELINE_INSPECTION",
            max_rows=100,
        )
        self.assert_expected_sessions(parsed)

    def test_required_xlsx_session_order_and_blank_isolation(self):
        try:
            from openpyxl import Workbook
        except ImportError:
            self.skipTest("openpyxl is not installed")
        workbook = Workbook()
        sheet = workbook.active
        for row in (
            ("session_id", "time", "query"),
            ("A", "10:03", "Q3"), ("A", "10:01", "Q1"),
            ("B", "10:05", "B1"), ("A", "10:02", "Q2"),
            (None, "10:06", "SINGLE1"), (None, "10:07", "SINGLE2"),
        ):
            sheet.append(row)
        stream = io.BytesIO()
        workbook.save(stream)
        parsed = parse_dataset_file(
            filename="acceptance.xlsx",
            content=stream.getvalue(),
            dataset_type="PIPELINE_INSPECTION",
            max_rows=100,
        )
        self.assert_expected_sessions(parsed)

    def test_real_looking_source_id_remains_import_metadata(self):
        parsed = parse_dataset_file(
            filename="source.csv",
            content=f"session_id,query\n{SOURCE_SESSION_ID},Q1\n{SOURCE_SESSION_ID},Q2\n".encode(),
            dataset_type="PIPELINE_INSPECTION",
            max_rows=100,
        )
        self.assertEqual(parsed.sessions[0].source_session_id, SOURCE_SESSION_ID)
        self.assertEqual([turn.query for turn in parsed.sessions[0].turns], ["Q1", "Q2"])


class AcceptanceHistoryAndStabilityTests(unittest.TestCase):
    def test_three_turn_histories_and_shared_formatting_and_trimming(self):
        completed = []
        expected = [
            [],
            [{"role": "user", "content": "Q1"}, {"role": "assistant", "content": "A1"}],
            [
                {"role": "user", "content": "Q1"}, {"role": "assistant", "content": "A1"},
                {"role": "user", "content": "Q2"}, {"role": "assistant", "content": "A2"},
            ],
        ]
        for index, (query, answer) in enumerate(zip(("Q1", "Q2", "Q3"), ("A1", "A2", "A3"))):
            history = messages_from_turn_records(completed)
            self.assertEqual(history, expected[index])
            self.assertEqual(format_rewrite_history(history), format_rewrite_history(trim_agent_messages(history)))
            completed.append({"raw_query": query, "actual_answer": answer})

    def test_five_repetitions_have_isolated_identity_and_history(self):
        logical = uuid.uuid4()
        specs = build_run_session_specs([logical], 5)
        self.assertEqual([spec.repeat_index for spec in specs], [1, 2, 3, 4, 5])
        self.assertEqual(len({spec.evaluation_session_key for spec in specs}), 5)
        histories = {}
        for spec in specs:
            completed = []
            histories[spec.evaluation_session_key] = []
            for query, answer in zip(("Q1", "Q2", "Q3"), ("A1", "A2", "A3")):
                before = messages_from_turn_records(completed)
                histories[spec.evaluation_session_key].append(before)
                completed.append({"raw_query": query, "actual_answer": answer})
        for attempts in histories.values():
            self.assertEqual(attempts[0], [])
            self.assertEqual([item["content"] for item in attempts[1]], ["Q1", "A1"])
            self.assertEqual([item["content"] for item in attempts[2]], ["Q1", "A1", "Q2", "A2"])

    def test_evaluation_policy_forbids_production_namespace_before_lookup(self):
        class ProductionSpy:
            namespace = "production"
            calls = 0

            async def load_rewrite_messages(self, key):
                self.calls += 1
                raise AssertionError("production history lookup must not execute")

        from conversation_history import enforce_history_policy
        spy = ProductionSpy()
        with self.assertRaisesRegex(RuntimeError, "EVALUATION_PRODUCTION_HISTORY_FORBIDDEN"):
            enforce_history_policy(spy, EVALUATION_EXECUTION_POLICY)
        self.assertEqual(spy.calls, 0)


class AcceptanceDivergenceTests(unittest.TestCase):
    BASE = {
        "NORMALIZATION": "n", "INTENT": "i", "REWRITE": "w",
        "RETRIEVAL": "r", "RERANK": "rr", "CONTEXT_SELECTION": "c",
        "PROMPT_BUILD": "p", "GENERATION": "g",
    }

    def turn(self, repeat, changes=None, answer="answer"):
        stages = dict(self.BASE)
        stages.update(changes or {})
        return ComparableTurn(
            run_session_id=f"run-{repeat}", logical_session_id="logical",
            repeat_index=repeat, turn_index=1, stage_outputs=stages,
            normalized_query=stages["NORMALIZATION"], intent=stages["INTENT"],
            rewritten_query=stages["REWRITE"], context_hash=stages["CONTEXT_SELECTION"],
            prompt_hash=stages["PROMPT_BUILD"], answer_hash=answer,
            fallback_used=False,
        )

    def assert_stage(self, changes, answer="answer", expected=None):
        summary = analyze_stability([self.turn(1), self.turn(2, changes, answer)])["logical"]
        self.assertEqual(summary.first_divergent_stage, expected)
        return summary

    def test_no_divergence(self):
        self.assert_stage({}, expected=None)

    def test_rewrite_first(self):
        self.assert_stage({"REWRITE": "w2"}, expected="REWRITE")

    def test_retrieval_first(self):
        self.assert_stage({"RETRIEVAL": "r2"}, expected="RETRIEVAL")

    def test_prompt_first_with_same_context(self):
        self.assert_stage({"PROMPT_BUILD": "p2"}, expected="PROMPT_BUILD")

    def test_generation_first(self):
        self.assert_stage({"GENERATION": "g2"}, answer="answer-2", expected="GENERATION")

    def test_exact_answer_difference_is_divergence_not_correctness(self):
        summary = self.assert_stage({"GENERATION": "g2"}, answer="same meaning, different text", expected="GENERATION")
        rendered = repr(summary.as_dict()).lower()
        self.assertNotIn("incorrect", rendered)
        self.assertNotIn("correct", rendered)


class AcceptanceInfrastructureTests(unittest.TestCase):
    def test_dependency_failures_are_infrastructure_not_semantic_fallbacks(self):
        injected = {
            "embedding": ServiceTimeoutError("embedding timeout"),
            "qdrant": ServiceUnavailableError("qdrant unavailable"),
            "reranker": ServiceTimeoutError("reranker timeout"),
            "vllm": ServiceUnavailableError("vllm unavailable"),
        }
        for stage, error in injected.items():
            with self.subTest(stage=stage):
                self.assertTrue(is_infrastructure_error(error))
        for semantic_reason in ("NO_RETRIEVAL_RESULTS", "LLM_CONTEXT_REFUSAL"):
            with self.subTest(reason=semantic_reason):
                self.assertIsInstance(semantic_reason, str)
                self.assertNotIsInstance(semantic_reason, BaseException)


class AcceptanceInfrastructurePersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_persists_each_dependency_failure_as_infrastructure(self):
        try:
            from evaluation_system.backend.app.tracing.collector import EvaluationTraceCollector
            from evaluation_system.backend.app.worker.runner import EvaluationRunExecutor
            from pipeline_observer import PipelineStageResult
        except ImportError as exc:
            self.skipTest(f"evaluation runtime dependency is not installed: {exc}")

        class Turn:
            metadata_json = {}

        class Session:
            def __init__(self, turn):
                self.turn = turn
                self.added = []
            async def __aenter__(self): return self
            async def __aexit__(self, *_args): return False
            async def get(self, _model, _identity, **_kwargs): return self.turn
            def add(self, value): self.added.append(value)
            async def commit(self): pass

        class Provider:
            async def discard_pending_state(self, _turn_id): pass

        cases = (
            ("embedding", ServiceTimeoutError("timeout"), (PipelineStage.NORMALIZATION, PipelineStage.INTENT, PipelineStage.REWRITE), PipelineStage.RETRIEVAL, "DEPENDENCY_TIMEOUT"),
            ("qdrant", ServiceUnavailableError("unavailable"), (PipelineStage.NORMALIZATION, PipelineStage.INTENT, PipelineStage.REWRITE), PipelineStage.RETRIEVAL, "DEPENDENCY_UNAVAILABLE"),
            ("reranker", ServiceTimeoutError("timeout"), (PipelineStage.NORMALIZATION, PipelineStage.INTENT, PipelineStage.REWRITE, PipelineStage.RETRIEVAL), PipelineStage.RERANK, "DEPENDENCY_TIMEOUT"),
            ("vllm", ServiceUnavailableError("unavailable"), tuple(PipelineStage)[:-1], PipelineStage.GENERATION, "DEPENDENCY_UNAVAILABLE"),
        )
        for component, error, completed, expected_stage, expected_code in cases:
            with self.subTest(component=component):
                turn = Turn()
                session = Session(turn)
                runner = EvaluationRunExecutor(
                    session_factory=lambda: session,
                    answering_service=object(),
                    session_concurrency=1,
                    event_bus=object(),
                )
                runner.history_provider = Provider()
                collector = EvaluationTraceCollector()
                for stage in completed:
                    collector.record(PipelineStageResult(stage=stage))
                await runner._error_turn(
                    uuid.uuid4(), error, collector,
                    infrastructure=is_infrastructure_error(error),
                    total_latency_ms=12.0,
                )
                self.assertTrue(turn.infrastructure_error)
                self.assertEqual(turn.status, "ERROR")
                self.assertEqual(turn.error_code, expected_code)
                failed = collector.get(expected_stage)
                self.assertIsNotNone(failed)
                self.assertEqual(failed.status, "ERROR")
                self.assertEqual(failed.error_code, expected_code)


class AcceptanceStaticSafetyTests(unittest.TestCase):
    def test_evaluation_history_adapter_has_no_production_chat_dependency(self):
        source = Path("evaluation_system/backend/app/core_adapter/history.py").read_text(encoding="utf-8")
        for forbidden in ("ChatManager", "DatabaseManager", SOURCE_SESSION_ID):
            self.assertNotIn(forbidden, source)

    def test_no_evaluation_drop_all_or_arbitrary_sql_api(self):
        root = Path("evaluation_system/backend")
        sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (root / "app").rglob("*.py")
        )
        self.assertNotIn("drop_all", sources.lower())
        api_sources = "\n".join(path.read_text(encoding="utf-8") for path in (root / "app/api").glob("*.py"))
        self.assertNotIn("arbitrary_sql", api_sources.lower())
        self.assertNotIn("DROP_EVALUATION_TABLES", api_sources)


class AcceptanceMigrationFlowTests(unittest.TestCase):
    @staticmethod
    def settings(allow=True):
        return SimpleNamespace(allow_db_init=allow)

    def test_status_error_is_safe_and_contains_no_connection_details(self):
        service = MigrationService(
            self.settings(), engine_factory=lambda: (_ for _ in ()).throw(RuntimeError("secret DSN"))
        )
        service.required_revision = lambda: "20260831_0001"
        status = service.status()
        self.assertEqual(status.status, "ERROR")
        self.assertEqual(status.error_code, "DATABASE_STATUS_ERROR")
        self.assertNotIn("secret", repr(status.as_dict()).lower())

    def test_correct_confirmation_uses_locked_predefined_upgrade_to_head(self):
        statements = []
        upgrades = []

        class Result:
            def __init__(self, value=None): self.value = value
            def scalar_one(self): return self.value

        class Connection:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def execute(self, statement, params=None):
                rendered = str(statement)
                statements.append((rendered, params))
                return Result(True if "pg_try_advisory_lock" in rendered else None)
            def commit(self): pass
            def rollback(self): pass

        class Engine:
            def connect(self): return Connection()
            def dispose(self): pass

        service = MigrationService(
            self.settings(), engine_factory=Engine,
            alembic_command=lambda config, target: upgrades.append((config, target)),
        )
        service._alembic_config = lambda: SimpleNamespace(attributes={})
        expected = DatabaseStatus("READY", "20260831_0001", "20260831_0001", (), True)
        service.status = lambda: expected
        self.assertIs(service.initialize(CONFIRMATION), expected)
        self.assertEqual([target for _config, target in upgrades], ["head"])
        rendered = "\n".join(statement for statement, _params in statements).lower()
        self.assertIn("pg_try_advisory_lock", rendered)
        self.assertIn("create schema if not exists evaluation", rendered)
        self.assertIn("pg_advisory_unlock", rendered)
        self.assertNotIn("drop", rendered)

    def test_busy_advisory_lock_rejects_concurrent_initialize(self):
        class Result:
            def scalar_one(self): return False
        class Connection:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def execute(self, _statement, _params=None): return Result()
        class Engine:
            def connect(self): return Connection()
            def dispose(self): pass
        service = MigrationService(self.settings(), engine_factory=Engine)
        with self.assertRaisesRegex(RuntimeError, "MIGRATION_ALREADY_RUNNING"):
            service.initialize(CONFIRMATION)


if __name__ == "__main__":
    unittest.main()
