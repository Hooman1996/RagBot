from __future__ import annotations

import copy
import json
import struct
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
from io import StringIO
from pathlib import Path

from scripts.kb_signature import compare_signatures, main as signature_main
from scripts.retrieval_stability import analyze_runs
from utils.read_only_audit import (
    canonical_sha256,
    vector_float32_le_signature,
)


def _signature() -> dict:
    postgres_record = {
        "chunk_id": "1",
        "document_id": "10",
        "chunk_index": 0,
        "document_title_sha256": "title-hash",
        "content_sha256": "content-hash",
        "metadata_sha256": "metadata-hash",
        "cross_store_metadata_sha256": "mapping-hash",
    }
    qdrant_record = {
        "logical_chunk_id": "1",
        "qdrant_point_id": "100",
        "document_id": "10",
        "chunk_index": 0,
        "document_title_sha256": "title-hash",
        "payload_metadata_sha256": "mapping-hash",
        "payload_sha256": "payload-hash",
        "payload_content_field": None,
        "content_sha256": None,
        "vector_present": True,
        "vectors": [{
            "name": "",
            "present": True,
            "dimension": 2,
            "sha256": "vector-hash",
        }],
    }
    return {
        "schema_version": 1,
        "generation": {"label": "dev", "generated_at": "ignored"},
        "postgres": {
            "record_count": 1,
            "aggregate_sha256": canonical_sha256([postgres_record]),
            "duplicate_logical_ids": [],
            "malformed_rows": [],
            "records": [postgres_record],
        },
        "qdrant": {
            "point_count": 1,
            "logical_aggregate_sha256": "logical-aggregate",
            "vector_aggregate_sha256": "vector-aggregate",
            "collection_config_sha256": canonical_sha256({
                "vectors": {"size": 2, "distance": "Cosine"}
            }),
            "collection_config": {
                "vectors": {"size": 2, "distance": "Cosine"}
            },
            "duplicate_logical_ids": [],
            "malformed_points": [],
            "missing_vector_ids": [],
            "records": [qdrant_record],
        },
        "cross_store": {"consistent": True},
    }


def _score(value: float) -> dict:
    return {
        "value": value,
        "ieee754_float64_le_hex": struct.pack("<d", value).hex(),
    }


def _run() -> dict:
    return {
        "embedding": {"dimension": 2, "sha256": "embedding-hash"},
        "hybrid_top": [{
            "chunk_id": "1",
            "content_sha256": "content-hash",
            "bm25_score": _score(0.2),
            "semantic_score": _score(0.3),
            "hybrid_score": _score(0.4),
        }],
        "rerank_top": [{
            "chunk_id": "1",
            "content_sha256": "content-hash",
            "reranker_score": _score(0.5),
        }],
    }


class AuditPrimitiveTests(unittest.TestCase):
    def test_canonical_hash_ignores_dictionary_insertion_order(self):
        self.assertEqual(
            canonical_sha256({"a": 1, "b": 2}),
            canonical_sha256({"b": 2, "a": 1}),
        )

    def test_vector_hash_is_float32_little_endian(self):
        expected = sha256(struct.pack("<ff", 1.0, -2.5)).hexdigest()
        self.assertEqual(
            vector_float32_le_signature([1.0, -2.5]),
            {"dimension": 2, "sha256": expected},
        )


class SignatureComparatorTests(unittest.TestCase):
    def test_internal_qdrant_point_id_does_not_break_full_match(self):
        left = _signature()
        right = copy.deepcopy(left)
        right["generation"]["label"] = "prod"
        right["qdrant"]["records"][0]["qdrant_point_id"] = "999"

        report = compare_signatures(left, right)

        self.assertTrue(report["status"]["FULL_MATCH"])
        self.assertEqual(
            len(report["differences"][
                "qdrant_point_id_mismatches_diagnostic_only"
            ]),
            1,
        )

    def test_content_vector_and_collection_differences_are_pinpointed(self):
        left = _signature()
        right = copy.deepcopy(left)
        right["postgres"]["records"][0]["content_sha256"] = "different"
        right["postgres"]["aggregate_sha256"] = "different-aggregate"
        right["qdrant"]["records"][0]["vectors"][0]["dimension"] = 3
        right["qdrant"]["records"][0]["vectors"][0]["sha256"] = "different"
        right["qdrant"]["vector_aggregate_sha256"] = "different-vector"
        right["qdrant"]["collection_config"]["vectors"]["distance"] = "Dot"
        right["qdrant"]["collection_config_sha256"] = "different-config"

        report = compare_signatures(left, right)

        self.assertFalse(report["status"]["FULL_MATCH"])
        self.assertEqual(
            report["differences"]["content_mismatches"][0]["chunk_id"],
            "1",
        )
        self.assertEqual(
            report["differences"]["vector_dimension_mismatches"][0][
                "chunk_id"
            ],
            "1",
        )
        self.assertEqual(
            report["differences"]["vector_hash_mismatches"][0]["chunk_id"],
            "1",
        )
        self.assertEqual(
            report["differences"]["collection_config_mismatches"][0][
                "field"
            ],
            "vectors.distance",
        )

    def test_compare_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            left = root / "left.json"
            right = root / "right.json"
            left.write_text(json.dumps(_signature()), encoding="utf-8")
            right.write_text(json.dumps(_signature()), encoding="utf-8")
            with redirect_stdout(StringIO()):
                self.assertEqual(signature_main([
                    "compare", str(left), str(right)
                ]), 0)

            changed = _signature()
            changed["cross_store"]["consistent"] = False
            right.write_text(json.dumps(changed), encoding="utf-8")
            with redirect_stdout(StringIO()):
                self.assertEqual(signature_main([
                    "compare", str(left), str(right)
                ]), 1)

            with redirect_stderr(StringIO()):
                self.assertEqual(signature_main([
                    "compare", str(root / "missing"), str(right)
                ]), 2)


class RetrievalStabilityAnalysisTests(unittest.TestCase):
    def test_identical_runs_are_exactly_stable(self):
        report = analyze_runs([_run(), copy.deepcopy(_run())])
        self.assertTrue(report["OVERALL_EXACT_STABLE"])
        self.assertEqual(report["FIRST_UNSTABLE_STAGE"], "NONE")

    def test_first_unstable_stage_and_score_drift_are_reported(self):
        baseline = _run()
        changed = copy.deepcopy(baseline)
        changed["hybrid_top"][0]["semantic_score"] = _score(0.3000001)

        report = analyze_runs([baseline, changed])

        self.assertFalse(report["OVERALL_EXACT_STABLE"])
        self.assertEqual(
            report["FIRST_UNSTABLE_STAGE"], "HYBRID_RETRIEVAL_SCORES"
        )
        self.assertGreater(
            report["drift"]["maximum_absolute_semantic_score_difference"],
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
