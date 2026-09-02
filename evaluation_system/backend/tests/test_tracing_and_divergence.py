from __future__ import annotations

import unittest

from pipeline_observer import (
    PipelineStage,
    PipelineStageResult,
    bind_pipeline_observer,
    emit_pipeline_stage_lazy,
)
from evaluation_system.backend.app.services.divergence import ComparableTurn, analyze_stability
from evaluation_system.backend.app.services.events import safe_error_code
from evaluation_system.backend.app.services.failures import is_infrastructure_error
from evaluation_system.backend.app.tracing.collector import EvaluationTraceCollector
from utils.request_instrumentation import RequestTrace, trace_summary
from utils.service_errors import InvalidRequestError, ServiceUnavailableError


class TraceTests(unittest.TestCase):
    def test_required_stage_set_is_complete(self):
        self.assertEqual(
            {stage.value for stage in PipelineStage},
            {
                "NORMALIZATION", "INTENT", "REWRITE", "RETRIEVAL",
                "RERANK", "CONTEXT_SELECTION", "PROMPT_BUILD", "GENERATION",
            },
        )

    def test_collector_merges_full_retrieval_artifacts(self):
        collector = EvaluationTraceCollector()
        collector.record(PipelineStageResult(
            stage=PipelineStage.RETRIEVAL,
            input_data={"query": "secret query"},
            output_data={"candidates": [{"chunk_id": "1", "rank": 1, "score": 0.8, "content": "banking content"}]},
            duration_ms=2.5,
        ))
        record = collector.get(PipelineStage.RETRIEVAL)
        self.assertEqual(record.output_data["candidates"][0]["chunk_id"], "1")
        self.assertIsNotNone(record.input_hash)
        self.assertIsNotNone(record.output_hash)

    def test_request_trace_remains_content_free(self):
        trace = RequestTrace(request_id="r", process_id=1)
        summary = trace_summary(trace)
        rendered = repr(summary)
        self.assertNotIn("prompt", rendered)
        self.assertNotIn("banking content", rendered)

    def test_production_noop_does_not_materialize_content_artifacts(self):
        calls = []

        def artifact_factory():
            calls.append("called")
            return PipelineStageResult(stage=PipelineStage.PROMPT_BUILD)

        emit_pipeline_stage_lazy(artifact_factory)
        self.assertEqual(calls, [])

        collector = EvaluationTraceCollector()
        with bind_pipeline_observer(collector):
            emit_pipeline_stage_lazy(artifact_factory)
        self.assertEqual(calls, ["called"])
        self.assertIsNotNone(collector.get(PipelineStage.PROMPT_BUILD))

    def test_error_and_fallback_are_distinct(self):
        collector = EvaluationTraceCollector()
        collector.record(PipelineStageResult(
            stage=PipelineStage.GENERATION, status="ERROR",
            error_code="DEPENDENCY_TIMEOUT", error_data={"error_type": "ServiceTimeoutError"},
        ))
        record = collector.get(PipelineStage.GENERATION)
        self.assertEqual(record.status, "ERROR")
        self.assertEqual(record.error_code, "DEPENDENCY_TIMEOUT")
        self.assertNotIn("fallback_used", record.metrics)

    def test_fallback_reason_and_infrastructure_are_distinct(self):
        collector = EvaluationTraceCollector()
        collector.record(PipelineStageResult(
            stage=PipelineStage.GENERATION,
            output_data={"answer": "fallback"},
            metrics={"fallback_used": True, "fallback_reason": "NO_RESULTS"},
        ))
        self.assertEqual(
            collector.get(PipelineStage.GENERATION).metrics["fallback_reason"],
            "NO_RESULTS",
        )
        self.assertTrue(
            is_infrastructure_error(ServiceUnavailableError("unavailable"))
        )
        self.assertFalse(
            is_infrastructure_error(InvalidRequestError("invalid"))
        )

    def test_event_error_codes_cannot_carry_content(self):
        self.assertEqual(safe_error_code("DEPENDENCY_TIMEOUT"), "DEPENDENCY_TIMEOUT")
        self.assertEqual(
            safe_error_code("query=customer content", fallback="EVALUATION_ERROR"),
            "EVALUATION_ERROR",
        )


class DivergenceTests(unittest.TestCase):
    def make(self, repeat, rewrite_hash, answer_hash):
        return ComparableTurn(
            run_session_id=f"r{repeat}", logical_session_id="logical",
            repeat_index=repeat, turn_index=1,
            stage_outputs={
                "NORMALIZATION": "n", "INTENT": "i", "REWRITE": rewrite_hash,
                "RETRIEVAL": "ret", "RERANK": "rr", "CONTEXT_SELECTION": "ctx",
                "PROMPT_BUILD": "p", "GENERATION": answer_hash,
            },
            normalized_query="q", intent="general", rewritten_query=rewrite_hash,
            context_hash="ctx", answer_hash=answer_hash, fallback_used=False,
        )

    def test_first_divergent_stage_is_not_labeled_error(self):
        summary = analyze_stability([self.make(1, "rw1", "a1"), self.make(2, "rw2", "a2")])["logical"]
        self.assertEqual(summary.first_divergent_turn, 1)
        self.assertEqual(summary.first_divergent_stage, "REWRITE")
        self.assertNotIn("error", repr(summary.as_dict()).lower())

    def test_failed_repetition_is_incomparable_not_divergence(self):
        successful = self.make(1, "rw1", "a1")
        failed = ComparableTurn(
            **{
                **self.make(2, "rw2", "a2").__dict__,
                "completed": False,
            }
        )
        summary = analyze_stability([successful, failed])["logical"]
        self.assertIsNone(summary.first_divergent_stage)
        self.assertEqual(summary.incomparable_turn_count, 1)


if __name__ == "__main__":
    unittest.main()
