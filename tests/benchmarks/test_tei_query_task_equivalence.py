import importlib.util
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "benchmarks"
    / "embedding"
    / "tei_query_task_equivalence.py"
)
SPEC = importlib.util.spec_from_file_location("tei_query_task_equivalence", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_cosine_rejects_dimension_mismatch():
    with pytest.raises(ValueError, match="dimension mismatch"):
        MODULE.cosine([1.0], [1.0, 0.0])


def test_overlap_at_10_uses_fixed_denominator():
    assert MODULE.overlap_at_k(list(range(10)), list(range(5, 15)), 10) == 0.5


def test_rank_and_score_changes_reports_shared_and_missing_points():
    baseline = [{"id": 1, "score": 0.8}, {"id": 2, "score": 0.7}]
    candidate = [{"id": 2, "score": 0.75}, {"id": 3, "score": 0.6}]

    changes = {item["id"]: item for item in MODULE.rank_and_score_changes(baseline, candidate)}

    assert changes[2]["rank_delta"] == -1
    assert changes[2]["score_delta"] == pytest.approx(0.05)
    assert changes[1]["candidate_rank"] is None
    assert changes[3]["a_rank"] is None


def test_retrieval_metrics_support_multiple_relevant_ids():
    queries = [
        {"id": "q1", "relevant_ids": [2, 4]},
        {"id": "q2", "relevant_ids": [8]},
    ]
    results = {
        "q1": [{"id": 2}, {"id": 9}, {"id": 4}],
        "q2": [{"id": 1}, {"id": 8}, {"id": 3}],
    }

    metrics = MODULE.retrieval_metrics(queries, results)

    assert metrics["top_1_accuracy"] == 0.5
    assert metrics["top_3_accuracy"] == 1.0
    assert metrics["recall_at_3"] == 1.0
    assert metrics["recall_at_10"] == 1.0
    assert metrics["mrr_at_10"] == 0.75


def test_validate_vectors_rejects_inconsistent_dimensions():
    with pytest.raises(ValueError, match="inconsistent output dimensions"):
        MODULE.validate_vectors([[1.0], [1.0, 2.0]], 2, "test")
