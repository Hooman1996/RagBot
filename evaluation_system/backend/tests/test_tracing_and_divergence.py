from __future__ import annotations

import unittest

from evaluation_system.backend.app.services.divergence import (
    ComparableTurn,
    analyze_stability,
)
from evaluation_system.backend.app.services.error_codes import safe_error_code
from evaluation_system.backend.app.services.pipeline_contract import (
    CANONICAL_STAGE_NAMES,
    STAGE_ORDER,
)


class TransportStageContractTests(unittest.TestCase):
    def test_required_stage_order_is_complete_and_canonical(self):
        self.assertEqual(
            CANONICAL_STAGE_NAMES,
            (
                "NORMALIZATION",
                "HISTORY",
                "REWRITE",
                "INTENT",
                "RETRIEVAL",
                "RERANK",
                "CONTEXT_SELECTION",
                "PROMPT_BUILD",
                "GENERATION",
            ),
        )
        self.assertEqual(
            STAGE_ORDER,
            {
                stage_name: index * 10
                for index, stage_name in enumerate(
                    CANONICAL_STAGE_NAMES, start=1
                )
            },
        )

    def test_event_error_codes_cannot_carry_content(self):
        self.assertEqual(safe_error_code("DEPENDENCY_TIMEOUT"), "DEPENDENCY_TIMEOUT")
        self.assertEqual(
            safe_error_code("query=customer content", fallback="EVALUATION_ERROR"),
            "EVALUATION_ERROR",
        )


class DivergenceTests(unittest.TestCase):
    def make(
        self,
        repeat,
        *,
        turn_index=1,
        rewrite_hash="rw",
        answer_hash="answer",
        fallback=False,
        completed=True,
    ):
        return ComparableTurn(
            run_session_id=f"r{repeat}",
            logical_session_id="logical",
            repeat_index=repeat,
            turn_index=turn_index,
            stage_outputs={
                "NORMALIZATION": "n",
                "HISTORY": "h",
                "REWRITE": rewrite_hash,
                "INTENT": "i",
                "RETRIEVAL": "ret",
                "RERANK": "rr",
                "CONTEXT_SELECTION": "ctx",
                "PROMPT_BUILD": "p",
                "GENERATION": answer_hash,
            },
            normalized_query="q",
            intent="general",
            rewritten_query=rewrite_hash,
            context_hash="ctx",
            answer_hash=answer_hash,
            fallback_used=fallback,
            completed=completed,
        )

    def test_first_divergent_turn_and_stage_follow_canonical_order(self):
        turns = [
            self.make(1, turn_index=1),
            self.make(2, turn_index=1),
            self.make(1, turn_index=2, rewrite_hash="rw1", answer_hash="a1"),
            self.make(2, turn_index=2, rewrite_hash="rw2", answer_hash="a2"),
        ]
        summary = analyze_stability(turns)["logical"]
        self.assertEqual(summary.first_divergent_turn, 2)
        self.assertEqual(summary.first_divergent_stage, "REWRITE")

    def test_variant_counts_and_fallback_rate_are_preserved(self):
        turns = [
            self.make(1, answer_hash="a1", fallback=True),
            self.make(2, answer_hash="a2"),
        ]
        summary = analyze_stability(turns)["logical"].as_dict()
        self.assertEqual(summary["fallback_count"], 1)
        self.assertEqual(summary["fallback_rate"], 0.5)
        self.assertEqual(summary["variant_counts"]["answer"], 2)

    def test_failed_repetition_is_incomparable_not_divergence(self):
        turns = [self.make(1), self.make(2, rewrite_hash="other", completed=False)]
        summary = analyze_stability(turns)["logical"]
        self.assertIsNone(summary.first_divergent_stage)
        self.assertEqual(summary.incomparable_turn_count, 1)


if __name__ == "__main__":
    unittest.main()
