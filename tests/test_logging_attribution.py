"""Outcome selection must not mistake HTTP 200 Eval failures for RAG success."""

import unittest

from benchmarks.structured_logging_attribution import (
    common_success, distribution, eval_category, percentile, semantic_metadata,
)


class AttributionAnalysisTests(unittest.TestCase):
    def test_eval_outcomes_require_application_completion(self):
        self.assertEqual(eval_category(200, {"status": "COMPLETED"}), "COMPLETED")
        self.assertEqual(eval_category(200, {
            "status": "ERROR", "error_code": "DEPENDENCY_UNAVAILABLE",
        }), "DEPENDENCY_UNAVAILABLE")
        self.assertEqual(eval_category(200, {"status": "ERROR"}), "OTHER_FAILURE")
        self.assertEqual(eval_category(500, {"status": "COMPLETED"}), "OTHER_FAILURE")

    def test_common_success_excludes_mixed_outcomes_and_matches_payloads(self):
        def row(index, category, latency):
            return {"index": index, "category": category, "latency_ms": latency,
                    "payload_hash": str(index)}

        baseline = {"corpus_hash": "shared", "rows": [
            row(0, "COMPLETED", 100), row(1, "DEPENDENCY_UNAVAILABLE", 1),
            row(2, "COMPLETED", 300),
        ]}
        feature = {"corpus_hash": "shared", "rows": [
            row(0, "COMPLETED", 110), row(1, "COMPLETED", 1000),
            row(2, "COMPLETED", 330),
        ]}
        result = common_success(baseline, feature)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["baseline"]["mean_ms"], 200)
        self.assertEqual(result["feature"]["mean_ms"], 220)
        feature["rows"][0]["payload_hash"] = "different-input"
        with self.assertRaises(ValueError):
            common_success(baseline, feature)
        feature["corpus_hash"] = "different-corpus"
        with self.assertRaises(ValueError):
            common_success(baseline, feature)

    def test_percentiles_interpolate_and_empty_sets_do_not_invent_latency(self):
        self.assertEqual(percentile([0, 100], .95), 95)
        self.assertEqual(distribution([]), {"count": 0})

    def test_semantic_artifact_retains_hashes_and_numeric_scores_only(self):
        data = {"answer": "synthetic answer content", "intent": "general",
                "stages": [{"stage_name": "RERANK", "status": "COMPLETED",
                            "output_data": {"rankings": [{
                                "content": "synthetic document text", "score": .25,
                            }]}}]}
        first = semantic_metadata(data)
        data["stages"][0]["output_data"]["rankings"][0]["score"] = .25001
        second = semantic_metadata(data)
        self.assertNotIn("synthetic answer content", str(first))
        self.assertNotIn("synthetic document text", str(first))
        self.assertEqual(first["stages"]["RERANK"]["output_without_scores_hash"],
                         second["stages"]["RERANK"]["output_without_scores_hash"])
        self.assertNotEqual(first["stages"]["RERANK"]["scores"],
                            second["stages"]["RERANK"]["scores"])


if __name__ == "__main__":
    unittest.main()
