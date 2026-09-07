from __future__ import annotations

import builtins
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace
from unittest import mock

from answering_service import AnswerRequestContext, AnsweringService
from pipeline_observer import (
    CompositePipelineObserver,
    PipelineStage,
    PipelineStageResult,
    TerminalPipelineObserver,
    bind_pipeline_observer,
    emit_pipeline_stage_lazy,
    pipeline_hashes_enabled,
)
from utils.performance_config import (
    PipelineDebugSettings,
    load_pipeline_debug_settings,
)
from scripts.validate_environment import SPECS


FULL_SETTINGS = PipelineDebugSettings(enabled=True)


def make_observer(
    settings: PipelineDebugSettings = FULL_SETTINGS,
    *,
    request_id: str = "request-1",
    use_history: bool = True,
) -> TerminalPipelineObserver:
    observer = TerminalPipelineObserver(
        settings,
        raw_query="  cvv2 کارتمو چجوری ببینم؟  ",
        session_id="session-1",
        channel="web",
        use_history=use_history,
        request_id=request_id,
    )
    records = [
        PipelineStageResult(
            stage=PipelineStage.NORMALIZATION,
            input_data={"raw_query": "cvv2 کارتمو چجوری ببینم؟"},
            output_data={"normalized_query": "CVV2 کارتمو چجوری ببینم؟"},
            duration_ms=1.42,
        ),
        PipelineStageResult(
            stage=PipelineStage.HISTORY,
            output_data={
                "real_history_exists": True,
                "messages_used": [
                    {"role": "user", "content": "cvv2 را کجا ببینم؟"},
                    {"role": "assistant", "content": "پاسخ قبلی"},
                ],
                "formatted_history": "User: cvv2 را کجا ببینم؟\nAI: پاسخ قبلی",
            },
            duration_ms=2.10,
        ),
        PipelineStageResult(
            stage=PipelineStage.REWRITE,
            input_data={"original_query": "انقضا چی"},
            output_data={
                "rewritten_query": "تاریخ انقضای کارتم را چطور ببینم؟"
            },
            metrics={"rewrite_used": True},
            duration_ms=180.34,
        ),
        PipelineStageResult(
            stage=PipelineStage.INTENT,
            input_data={
                "classifier_input": "تاریخ انقضای کارتم را چطور ببینم؟"
            },
            output_data={
                "type": "general",
                "selected_class": "ACTIONABLE_INTENT",
                "class_id": 0,
                "p_actionable": 0.91,
                "p_chitchat": 0.09,
                "effective_threshold": 0.55,
            },
            duration_ms=8.73,
        ),
        PipelineStageResult(
            stage=PipelineStage.RETRIEVAL,
            output_data={
                "candidates": [
                    {
                        "rank": 1,
                        "chunk_id": "chunk-b",
                        "retrieval_score": 0.032,
                        "content": "candidate B",
                        "metadata": {"document_name": "cards.pdf", "page": 2},
                    },
                    {
                        "rank": 2,
                        "chunk_id": "chunk-a",
                        "retrieval_score": 0.031,
                        "content": "candidate A",
                        "metadata": {"document_name": "cards.pdf", "page": 3},
                    },
                ]
            },
            duration_ms=24.12,
        ),
        PipelineStageResult(
            stage=PipelineStage.RERANK,
            output_data={
                "rankings": [
                    {
                        "chunk_id": "chunk-a",
                        "original_rrf_rank": 2,
                        "hybrid_score": 0.031,
                        "reranker_score": 0.98,
                        "reranker_rank": 1,
                        "selected": True,
                        "content": "ABCDEFGHIJ",
                        "metadata": {"document_name": "cards.pdf", "page": 3},
                    },
                    {
                        "chunk_id": "chunk-b",
                        "original_rrf_rank": 1,
                        "hybrid_score": 0.032,
                        "reranker_score": 0.87,
                        "reranker_rank": 2,
                        "selected": True,
                        "content": "second reranked content",
                        "metadata": {"document_name": "cards.pdf", "page": 2},
                    },
                ]
            },
            metrics={"purpose": "answer_context", "selected_count": 2},
            duration_ms=32.45,
        ),
        PipelineStageResult(
            stage=PipelineStage.CONTEXT_SELECTION,
            input_data={"category": "FAQ"},
            output_data={
                "selected_chunk_ids": ["chunk-a", "chunk-b"],
                "selected_context": "exact generation context",
            },
            duration_ms=0.41,
        ),
        PipelineStageResult(
            stage=PipelineStage.PROMPT_BUILD,
            output_data={
                "system_message": "EXACT SYSTEM PROMPT",
                "user_prompt": "EXACT USER PROMPT",
                "prompt": [
                    {"role": "system", "content": "EXACT SYSTEM PROMPT"},
                    {"role": "user", "content": "EXACT USER PROMPT"},
                ],
            },
            duration_ms=0.22,
        ),
        PipelineStageResult(
            stage=PipelineStage.GENERATION,
            output_data={"answer": "کاربر گرامی، پاسخ کامل نهایی"},
            metrics={
                "model": "/app/model",
                "temperature": 0.0,
                "top_p": 1.0,
                "seed": 42,
                "max_tokens": 500,
            },
            duration_ms=450.12,
        ),
    ]
    for record in records:
        observer.record(record)
    return observer


def make_result(intent: str = "general") -> SimpleNamespace:
    return SimpleNamespace(
        normalized_query="CVV2 کارتمو چجوری ببینم؟",
        rewritten_query="تاریخ انقضای کارتم را چطور ببینم؟",
        canonical_retrieval_query="تاریخ انقضای کارت را چطور ببینم؟",
        final_retrieval_query="تاریخ انقضای کارت را چطور ببینم؟",
        intent=intent,
        answer="کاربر گرامی، پاسخ کامل نهایی",
        timings_ms={"graph": 720.5, "total": 730.25},
    )


class ImmediateRunner:
    async def run(self, function, /, *args, **kwargs):
        kwargs.pop("wait_for_completion_on_cancel", None)
        return function(*args, **kwargs)


class CountingProcessor:
    def __init__(self, counts):
        self.counts = counts

    def normalize(self, query):
        self.counts["normalization"] += 1
        return str(query).strip().replace("ي", "ی")


class CountingHistoryProvider:
    namespace = "test"

    def __init__(self, counts):
        self.counts = counts

    async def load_rewrite_messages(self, _key):
        self.counts["history"] += 1
        return [
            {"role": "user", "content": "پرسش قبلی"},
            {"role": "assistant", "content": "پاسخ قبلی"},
        ]


class CountingRewriter:
    def __init__(self, counts):
        self.counts = counts

    async def rewrite_query(self, *, current_query, current_summary):
        self.counts["rewrite"] += 1
        rewritten = f"بازنویسی {current_query}"
        emit_pipeline_stage_lazy(lambda: PipelineStageResult(
            stage=PipelineStage.REWRITE,
            input_data={
                "original_query": current_query,
                "history_used": current_summary,
            },
            output_data={"rewritten_query": rewritten},
            metrics={"rewrite_used": True},
            duration_ms=3.0,
        ))
        return rewritten


class CountingClassifier:
    threshold = 0.55

    def __init__(self, counts):
        self.counts = counts

    async def classify(self, query):
        self.counts["classifier"] += 1
        return {"type": "general", "scenario_id": None}


class CountingAgent:
    def __init__(self, counts):
        self.counts = counts

    def _artifact(self, result):
        self.counts["content_artifact_build"] += 1
        return result

    async def process_message_detailed(self, **kwargs):
        self.counts["embedding"] += 1
        self.counts["retrieval"] += 1
        self.counts["reranker"] += 1
        self.counts["generation"] += 1
        emit_pipeline_stage_lazy(lambda: self._artifact(PipelineStageResult(
            stage=PipelineStage.RETRIEVAL,
            output_data={"candidates": []},
            duration_ms=1.0,
        )))
        emit_pipeline_stage_lazy(lambda: PipelineStageResult(
            stage=PipelineStage.RERANK,
            output_data={"rankings": []},
            metrics={"purpose": "answer_context"},
            duration_ms=2.0,
        ))
        emit_pipeline_stage_lazy(lambda: PipelineStageResult(
            stage=PipelineStage.CONTEXT_SELECTION,
            input_data={"category": "FAQ"},
            output_data={"selected_chunk_ids": []},
            duration_ms=0.1,
        ))
        emit_pipeline_stage_lazy(lambda: PipelineStageResult(
            stage=PipelineStage.PROMPT_BUILD,
            output_data={
                "system_message": "system",
                "user_prompt": "actual prompt",
                "prompt": [
                    {"role": "system", "content": "system"},
                    {"role": "user", "content": "actual prompt"},
                ],
            },
        ))
        emit_pipeline_stage_lazy(lambda: PipelineStageResult(
            stage=PipelineStage.GENERATION,
            output_data={"answer": "actual complete answer"},
            metrics={
                "model": "fake-model", "temperature": 0.0, "top_p": 1.0,
                "seed": 42, "max_tokens": 50,
            },
            duration_ms=4.0,
        ))
        return SimpleNamespace(
            answer="actual complete answer",
            state={
                "messages": [
                    {"role": "user", "content": kwargs["user_message"]},
                    {"role": "assistant", "content": "actual complete answer"},
                ],
                "related_questions": [],
                "feedback_needed": True,
            },
            history_before=[{"role": "user", "content": "پرسش قبلی"}],
        )


def make_counting_service(settings):
    counts = {
        name: 0
        for name in (
            "normalization", "history", "rewrite", "classifier", "embedding",
            "retrieval", "reranker", "generation", "content_artifact_build",
        )
    }
    provider = CountingHistoryProvider(counts)
    service = AnsweringService(
        agent_service=CountingAgent(counts),
        intent_classifier=CountingClassifier(counts),
        history_rewriting_service=CountingRewriter(counts),
        text_processor=CountingProcessor(counts),
        blocking_runner=ImmediateRunner(),
        category_resolver=lambda _document: "FAQ",
        history_provider=provider,
        pipeline_debug_settings=settings,
    )
    return service, counts


class PipelineDebugSettingsTests(unittest.TestCase):
    def test_environment_validator_recognizes_every_debug_setting(self):
        expected = {
            "RAG_PIPELINE_DEBUG",
            "RAG_PIPELINE_DEBUG_QUERY",
            "RAG_PIPELINE_DEBUG_NORMALIZATION",
            "RAG_PIPELINE_DEBUG_HISTORY",
            "RAG_PIPELINE_DEBUG_REWRITE",
            "RAG_PIPELINE_DEBUG_INTENT",
            "RAG_PIPELINE_DEBUG_RETRIEVAL",
            "RAG_PIPELINE_DEBUG_RERANK",
            "RAG_PIPELINE_DEBUG_CONTEXT",
            "RAG_PIPELINE_DEBUG_PROMPT",
            "RAG_PIPELINE_DEBUG_ANSWER",
            "RAG_PIPELINE_DEBUG_TIMINGS",
            "RAG_PIPELINE_DEBUG_CHUNK_MAX_CHARS",
            "RAG_PIPELINE_DEBUG_FULL_CHUNKS",
        }
        self.assertTrue(expected.issubset(SPECS))

    def test_master_false_overrides_all_granular_true_values(self):
        settings = PipelineDebugSettings(
            enabled=False,
            query=True,
            normalization=True,
            history=True,
            rewrite=True,
            intent=True,
            retrieval=True,
            rerank=True,
            context=True,
            prompt=True,
            answer=True,
            timings=True,
        )
        for name in (
            "query", "normalization", "history", "rewrite", "intent",
            "retrieval", "rerank", "context", "prompt", "answer", "timings",
        ):
            self.assertFalse(settings.displays(name))

    def test_environment_parser_validates_nonnegative_chunk_limit(self):
        with mock.patch.dict(
            "os.environ", {"RAG_PIPELINE_DEBUG_CHUNK_MAX_CHARS": "-1"}, clear=False
        ):
            with self.assertRaisesRegex(ValueError, "must be at least 0"):
                load_pipeline_debug_settings()

    def test_environment_parser_applies_master_and_granular_values(self):
        with mock.patch.dict(
            "os.environ",
            {
                "RAG_PIPELINE_DEBUG": "false",
                "RAG_PIPELINE_DEBUG_QUERY": "true",
                "RAG_PIPELINE_DEBUG_PROMPT": "true",
            },
            clear=False,
        ):
            settings = load_pipeline_debug_settings()
        self.assertFalse(settings.displays("query"))
        self.assertFalse(settings.displays("prompt"))


class TerminalPipelineFormatterTests(unittest.TestCase):
    def test_enabled_report_has_actual_pipeline_values_and_ordering(self):
        report = make_observer().build_report(result=make_result())
        self.assertIn("RAGBOT PIPELINE", report)
        self.assertIn("cvv2 کارتمو چجوری ببینم؟", report)
        self.assertIn("CVV2 کارتمو چجوری ببینم؟", report)
        self.assertIn("Messages used : 2", report)
        self.assertIn("تاریخ انقضای کارتم را چطور ببینم؟", report)
        self.assertIn("classifier_input", repr(make_observer().records[3].input_data))
        self.assertIn("ACTIONABLE_INTENT", report)
        self.assertLess(report.index("chunk-b"), report.index("chunk-a"))
        rerank_section = report[report.index("[8] BGE RERANK"):]
        self.assertLess(rerank_section.index("chunk-a"), rerank_section.index("chunk-b"))
        self.assertIn("FINAL RETRIEVAL QUERY", report)

    def test_each_granular_switch_controls_its_section(self):
        section_names = {
            "query": "[1] USER QUERY",
            "normalization": "[2] NORMALIZATION",
            "history": "[3] HISTORY",
            "rewrite": "[4] QUERY REWRITE",
            "intent": "[5] INTENT CLASSIFICATION",
            "retrieval": "[7] HYBRID RETRIEVAL",
            "rerank": "[8] BGE RERANK",
            "context": "[9] CONTEXT SELECTION",
            "answer": "[11] FINAL ANSWER",
            "timings": "TIMINGS",
        }
        base = PipelineDebugSettings(
            enabled=True,
            query=False,
            normalization=False,
            history=False,
            rewrite=False,
            intent=False,
            retrieval=False,
            rerank=False,
            context=False,
            prompt=False,
            answer=False,
            timings=False,
        )
        for field, section in section_names.items():
            with self.subTest(field=field):
                disabled = make_observer(base).build_report(result=make_result())
                enabled = make_observer(
                    replace(base, **{field: True})
                ).build_report(result=make_result())
                self.assertNotIn(section, disabled)
                self.assertIn(section, enabled)

    def test_chunk_preview_truncation_is_display_only(self):
        settings = replace(FULL_SETTINGS, chunk_max_chars=4, full_chunks=False)
        observer = make_observer(settings)
        source_content = observer.records[5].output_data["rankings"][0]["content"]
        report = observer.build_report(result=make_result())
        self.assertIn("ABCD... [terminal preview truncated]", report)
        self.assertEqual(source_content, "ABCDEFGHIJ")

    def test_prompt_is_hidden_or_shown_without_rebuilding(self):
        hidden = make_observer(
            replace(FULL_SETTINGS, prompt=False)
        ).build_report(result=make_result())
        shown = make_observer(
            replace(FULL_SETTINGS, prompt=True)
        ).build_report(result=make_result())
        self.assertIn("System prompt chars : 19", hidden)
        self.assertIn("User prompt chars   : 17", hidden)
        self.assertNotIn("EXACT SYSTEM PROMPT", hidden)
        self.assertNotIn("EXACT USER PROMPT", hidden)
        self.assertIn("----- BEGIN SYSTEM PROMPT -----", shown)
        self.assertIn("----- END SYSTEM PROMPT -------", shown)
        self.assertIn("----- BEGIN USER PROMPT -------", shown)
        self.assertIn("----- END USER PROMPT ---------", shown)
        self.assertIn("EXACT SYSTEM PROMPT", shown)
        self.assertIn("EXACT USER PROMPT", shown)

    def test_final_answer_and_actual_timings_are_complete(self):
        report = make_observer().build_report(result=make_result())
        self.assertIn("کاربر گرامی، پاسخ کامل نهایی", report)
        self.assertIn("normalization        :      1.42 ms", report)
        self.assertIn("generation           :    450.12 ms", report)
        self.assertIn("graph                :    720.50 ms", report)
        self.assertIn("TOTAL                :    730.25 ms", report)

    def test_chitchat_marks_retrieval_rerank_and_context_skipped(self):
        observer = TerminalPipelineObserver(
            FULL_SETTINGS,
            raw_query="خیلی ممنون",
            session_id="s",
            channel="web",
            use_history=True,
            request_id="chat-1",
        )
        observer.record(PipelineStageResult(
            stage=PipelineStage.NORMALIZATION,
            input_data={"raw_query": "خیلی ممنون"},
            output_data={"normalized_query": "خیلی ممنون"},
        ))
        observer.record(PipelineStageResult(
            stage=PipelineStage.INTENT,
            input_data={"classifier_input": "خیلی ممنون"},
            output_data={"type": "chitchat"},
        ))
        for stage in (
            PipelineStage.RETRIEVAL,
            PipelineStage.RERANK,
            PipelineStage.CONTEXT_SELECTION,
        ):
            observer.record(PipelineStageResult(
                stage=stage,
                status="SKIPPED",
                metrics={"reason": "CHITCHAT", "purpose": "answer_context"},
                output_data={"candidates": [], "rankings": []},
                duration_ms=0.0,
            ))
        report = observer.build_report(result=make_result(intent="chitchat"))
        self.assertIn("[not used - chitchat]", report)
        self.assertEqual(report.count("SKIPPED - CHITCHAT"), 3)

    def test_formatter_and_printing_failures_are_swallowed(self):
        observer = make_observer()
        with mock.patch.object(observer, "build_report", side_effect=RuntimeError("bad")):
            observer.finish(result=make_result())
        observer = make_observer(request_id="request-2")
        with mock.patch("pipeline_observer._print_pipeline_report", side_effect=OSError("bad")):
            observer.finish(result=make_result())

    def test_terminal_observer_does_not_enable_evaluation_hashes(self):
        observer = make_observer()
        with bind_pipeline_observer(observer):
            self.assertFalse(pipeline_hashes_enabled())

    def test_composed_evaluation_observer_preserves_existing_hash_contract(self):
        class EvaluationObserver:
            def record(self, _result):
                return None

        observer = CompositePipelineObserver(make_observer(), EvaluationObserver())
        with bind_pipeline_observer(observer):
            self.assertTrue(pipeline_hashes_enabled())


class AnsweringServiceTerminalDebugTests(unittest.IsolatedAsyncioTestCase):
    async def test_master_disabled_has_no_output_and_builds_no_terminal_observer(self):
        service, counts = make_counting_service(PipelineDebugSettings(enabled=False))
        with mock.patch("answering_service.TerminalPipelineObserver") as terminal, mock.patch(
            "builtins.print"
        ) as stdout:
            result = await service.answer(AnswerRequestContext(
                original_query="سوال",
                selected_documents=("General_FAQ",),
                session_id="12",
            ))
        self.assertEqual(result.answer, "actual complete answer")
        terminal.assert_not_called()
        stdout.assert_not_called()
        self.assertEqual(counts["generation"], 1)
        self.assertEqual(counts["content_artifact_build"], 0)

    async def test_enabled_outputs_one_report_and_does_not_duplicate_pipeline_calls(self):
        service, counts = make_counting_service(FULL_SETTINGS)
        reports = []
        with mock.patch("pipeline_observer._print_pipeline_report", reports.append):
            result = await service.answer(AnswerRequestContext(
                original_query="  يک سوال  ",
                selected_documents=("General_FAQ",),
                session_id="12",
            ))
        self.assertEqual(result.answer, "actual complete answer")
        self.assertEqual(len(reports), 1)
        self.assertIn("actual complete answer", reports[0])
        self.assertIn("بازنویسی یک سوال", reports[0])
        for name, count in counts.items():
            with self.subTest(name=name):
                self.assertEqual(count, 1)

    async def test_debug_failure_cannot_fail_successful_request(self):
        service, _counts = make_counting_service(FULL_SETTINGS)
        with mock.patch(
            "pipeline_observer.TerminalPipelineObserver.build_report",
            side_effect=RuntimeError("formatter failed"),
        ):
            result = await service.answer(AnswerRequestContext(
                original_query="سوال",
                selected_documents=("General_FAQ",),
                session_id="12",
            ))
        self.assertEqual(result.answer, "actual complete answer")

    async def test_request_error_is_reported_and_original_exception_is_preserved(self):
        service, _counts = make_counting_service(FULL_SETTINGS)
        failure = RuntimeError("original request failure")

        async def fail(**_kwargs):
            raise failure

        service.agent_service.process_message_detailed = fail
        reports = []
        with mock.patch("pipeline_observer._print_pipeline_report", reports.append):
            with self.assertRaises(RuntimeError) as caught:
                await service.answer(AnswerRequestContext(
                    original_query="سوال",
                    selected_documents=("General_FAQ",),
                    session_id="12",
                ))
        self.assertIs(caught.exception, failure)
        self.assertEqual(len(reports), 1)
        self.assertIn("ERROR", reports[0])
        self.assertIn("original request failure", reports[0])


class TerminalOutputSafetyTests(unittest.TestCase):
    def test_no_file_api_or_file_handler_is_used(self):
        observer = make_observer()
        with mock.patch.object(builtins, "open", side_effect=AssertionError("file write")), mock.patch(
            "pipeline_observer._print_pipeline_report"
        ) as stdout:
            observer.finish(result=make_result())
        stdout.assert_called_once()

        inspect_module = __import__("inspect")
        module_source = inspect_module.getsource(__import__("pipeline_observer"))
        for forbidden in (
            "FileHandler", "RotatingFileHandler", "TimedRotatingFileHandler",
            "write_text", "open(",
        ):
            self.assertNotIn(forbidden, module_source)
        terminal_source = inspect_module.getsource(TerminalPipelineObserver)
        for forbidden in ("sha256", "stable_hash"):
            self.assertNotIn(forbidden, terminal_source)

    def test_concurrent_reports_are_single_noninterleaved_print_calls(self):
        active = 0
        maximum_active = 0
        calls = []
        state_lock = threading.Lock()

        def guarded_print(report, *, flush):
            nonlocal active, maximum_active
            with state_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.01)
            calls.append((report, flush))
            with state_lock:
                active -= 1

        observers = [make_observer(request_id=f"request-{index}") for index in range(8)]
        with mock.patch("builtins.print", side_effect=guarded_print):
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda item: item.finish(result=make_result()), observers))

        self.assertEqual(maximum_active, 1)
        self.assertEqual(len(calls), 8)
        self.assertTrue(all(flush for _report, flush in calls))
        for index, (report, _flush) in enumerate(calls):
            request_lines = [
                line for line in report.splitlines() if line.startswith("Request      :")
            ]
            self.assertEqual(len(request_lines), 1)
            self.assertRegex(request_lines[0], r"Request      : request-\d+")


if __name__ == "__main__":
    unittest.main()
