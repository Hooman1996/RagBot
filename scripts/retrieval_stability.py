#!/usr/bin/env python3
"""Run sequential, read-only exact-stability checks on RagBot retrieval.

Exit codes: 0 means OVERALL_EXACT_STABLE, 1 means completed with detected
instability, and 2 means an execution/configuration error.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from dotenv import load_dotenv

load_dotenv(REPOSITORY_ROOT / ".env", override=False)

import httpx
from qdrant_client import QdrantClient

from new_architecture.app.services.history.database import DatabaseManager
from utils.client_lifecycle import SerializedClient
from utils.concurrency import BoundedBlockingRunner
from utils.performance_config import PERFORMANCE_SETTINGS
from utils.persian_hybrid_search import PersianHybridSearch, PersianTextProcessor
from utils.persian_normalization import normalize_persian_text, query_fingerprint
from utils.rag_utils import chunk_fetcher_factory, chunk_revision_fetcher_factory
from utils.read_only_audit import (
    float64_le_hex,
    text_sha256,
    vector_float32_le_signature,
    write_json_report,
)
from utils.retrieval_query_canonicalizer import (
    RETRIEVAL_QUERY_ALIASES_PATH,
    RETRIEVAL_QUERY_ALIASES_SCHEMA_VERSION,
    RETRIEVAL_QUERY_ALIASES_SHA256,
    canonicalize_retrieval_query,
)


SCHEMA_VERSION = 1


def _score(value: Any) -> dict[str, Any]:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError("retrieval scores must be finite")
    return {
        "value": numeric,
        "ieee754_float64_le_hex": float64_le_hex(numeric),
    }


def _hybrid_records(results: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "rank": rank,
            "chunk_id": str(result.doc_id),
            "content_sha256": text_sha256(result.content),
            "bm25_score": _score(result.bm25_score),
            "semantic_score": _score(result.semantic_score),
            "hybrid_score": _score(result.score),
        }
        for rank, result in enumerate(results, start=1)
    ]


def _rerank_records(results: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "rank": rank,
            "chunk_id": str(result.doc_id),
            "content_sha256": text_sha256(result.content),
            "reranker_score": _score(result.reranker_score),
            "original_hybrid_rank": result.original_rrf_rank,
        }
        for rank, result in enumerate(results, start=1)
    ]


def _ids(run: dict[str, Any], key: str) -> list[str]:
    return [row["chunk_id"] for row in run[key]]


def _content_map(run: dict[str, Any], key: str) -> dict[str, str]:
    return {row["chunk_id"]: row["content_sha256"] for row in run[key]}


def _score_map(
    run: dict[str, Any], key: str, fields: tuple[str, ...]
) -> dict[str, tuple[str, ...]]:
    return {
        row["chunk_id"]: tuple(
            row[field]["ieee754_float64_le_hex"] for field in fields
        )
        for row in run[key]
    }


def _maximum_drift(
    baseline: dict[str, Any],
    current: dict[str, Any],
    section: str,
    score_field: str,
) -> float:
    left = {
        row["chunk_id"]: float(row[score_field]["value"])
        for row in baseline[section]
    }
    right = {
        row["chunk_id"]: float(row[score_field]["value"])
        for row in current[section]
    }
    return max(
        (abs(left[key] - right[key]) for key in set(left) & set(right)),
        default=0.0,
    )


def analyze_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if not runs:
        raise ValueError("at least one completed run is required")
    baseline = runs[0]
    conditions = {
        "QUERY_EMBEDDING_EXACT_STABLE": True,
        "HYBRID_TOP50_ID_ORDER_STABLE": True,
        "HYBRID_TOP50_CONTENT_STABLE": True,
        "HYBRID_TOP50_SCORES_EXACT_STABLE": True,
        "RERANK_TOP10_ID_ORDER_STABLE": True,
        "RERANK_TOP10_CONTENT_STABLE": True,
        "RERANK_SCORES_EXACT_STABLE": True,
    }
    drift = {
        "maximum_absolute_semantic_score_difference": 0.0,
        "maximum_absolute_bm25_score_difference": 0.0,
        "maximum_absolute_hybrid_score_difference": 0.0,
        "maximum_absolute_reranker_score_difference": 0.0,
    }
    hybrid_fields = ("bm25_score", "semantic_score", "hybrid_score")
    for current in runs[1:]:
        conditions["QUERY_EMBEDDING_EXACT_STABLE"] &= (
            current["embedding"]["dimension"]
            == baseline["embedding"]["dimension"]
            and current["embedding"]["sha256"]
            == baseline["embedding"]["sha256"]
        )
        conditions["HYBRID_TOP50_ID_ORDER_STABLE"] &= (
            _ids(current, "hybrid_top") == _ids(baseline, "hybrid_top")
        )
        conditions["HYBRID_TOP50_CONTENT_STABLE"] &= (
            _content_map(current, "hybrid_top")
            == _content_map(baseline, "hybrid_top")
        )
        conditions["HYBRID_TOP50_SCORES_EXACT_STABLE"] &= (
            _score_map(current, "hybrid_top", hybrid_fields)
            == _score_map(baseline, "hybrid_top", hybrid_fields)
        )
        conditions["RERANK_TOP10_ID_ORDER_STABLE"] &= (
            _ids(current, "rerank_top") == _ids(baseline, "rerank_top")
        )
        conditions["RERANK_TOP10_CONTENT_STABLE"] &= (
            _content_map(current, "rerank_top")
            == _content_map(baseline, "rerank_top")
        )
        conditions["RERANK_SCORES_EXACT_STABLE"] &= (
            _score_map(current, "rerank_top", ("reranker_score",))
            == _score_map(baseline, "rerank_top", ("reranker_score",))
        )
        drift["maximum_absolute_semantic_score_difference"] = max(
            drift["maximum_absolute_semantic_score_difference"],
            _maximum_drift(
                baseline, current, "hybrid_top", "semantic_score"
            ),
        )
        drift["maximum_absolute_bm25_score_difference"] = max(
            drift["maximum_absolute_bm25_score_difference"],
            _maximum_drift(baseline, current, "hybrid_top", "bm25_score"),
        )
        drift["maximum_absolute_hybrid_score_difference"] = max(
            drift["maximum_absolute_hybrid_score_difference"],
            _maximum_drift(baseline, current, "hybrid_top", "hybrid_score"),
        )
        drift["maximum_absolute_reranker_score_difference"] = max(
            drift["maximum_absolute_reranker_score_difference"],
            _maximum_drift(
                baseline, current, "rerank_top", "reranker_score"
            ),
        )

    stage_order = (
        ("QUERY_EMBEDDING_EXACT_STABLE", "QUERY_EMBEDDING"),
        ("HYBRID_TOP50_ID_ORDER_STABLE", "HYBRID_RETRIEVAL_IDS"),
        ("HYBRID_TOP50_CONTENT_STABLE", "HYBRID_RETRIEVAL_CONTENT"),
        ("HYBRID_TOP50_SCORES_EXACT_STABLE", "HYBRID_RETRIEVAL_SCORES"),
        ("RERANK_TOP10_ID_ORDER_STABLE", "RERANK_IDS"),
        ("RERANK_TOP10_CONTENT_STABLE", "RERANK_CONTENT"),
        ("RERANK_SCORES_EXACT_STABLE", "RERANK_SCORES"),
    )
    first_unstable = next(
        (stage for condition, stage in stage_order if not conditions[condition]),
        "NONE",
    )
    overall = all(conditions.values())
    return {
        **conditions,
        "OVERALL_EXACT_STABLE": overall,
        "FIRST_UNSTABLE_STAGE": first_unstable,
        "drift": drift,
    }


def _qdrant_client() -> SerializedClient:
    return SerializedClient(QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
        api_key=os.getenv("QDRANT_API_KEY"),
        https=os.getenv("QDRANT_HTTPS", "false").strip().lower() == "true",
        timeout=10.0,
    ))


async def run_stability(
    *,
    raw_query: str,
    run_count: int,
    retrieval_top_k: int,
    rerank_top_k: int,
    documents: list[str] | None = None,
) -> dict[str, Any]:
    if run_count < 2:
        raise ValueError("--runs must be at least 2")
    if retrieval_top_k < 1 or rerank_top_k < 1:
        raise ValueError("top-k values must be positive")
    if rerank_top_k > retrieval_top_k:
        raise ValueError("--rerank-top-k cannot exceed --retrieval-top-k")

    database = DatabaseManager()
    blocking = BoundedBlockingRunner(
        PERFORMANCE_SETTINGS.blocking_concurrency_limit
    )
    qdrant = _qdrant_client()
    timeout = httpx.Timeout(
        connect=PERFORMANCE_SETTINGS.tei_http_connect_timeout_seconds,
        read=PERFORMANCE_SETTINGS.tei_http_read_timeout_seconds,
        write=PERFORMANCE_SETTINGS.tei_http_write_timeout_seconds,
        pool=PERFORMANCE_SETTINGS.tei_http_pool_timeout_seconds,
    )
    limits = httpx.Limits(
        max_connections=PERFORMANCE_SETTINGS.tei_http_max_connections,
        max_keepalive_connections=(
            PERFORMANCE_SETTINGS.tei_http_max_keepalive_connections
        ),
        keepalive_expiry=(
            PERFORMANCE_SETTINGS.tei_http_keepalive_expiry_seconds
        ),
    )
    async_http = httpx.AsyncClient(timeout=timeout, limits=limits)
    sync_http = httpx.Client(timeout=timeout, limits=limits)
    search: PersianHybridSearch | None = None
    try:
        processor = await blocking.run(PersianTextProcessor, use_stemming=False)
        normalized_query = await blocking.run(processor.normalize, raw_query)
        normalized_query = normalize_persian_text(normalized_query.strip())
        if not normalized_query:
            raise ValueError("query is empty after normalization")
        canonical_query = canonicalize_retrieval_query(normalized_query)

        if documents:
            allowed_documents = database.filter_available_document_titles(
                documents
            )
            if len(allowed_documents) != len(dict.fromkeys(documents)):
                raise ValueError("one or more --document values are unavailable")
        else:
            rows = database.get_available_documents()
            allowed_documents = sorted(
                str(row["title"]) for row in rows if row.get("title")
            )
        if not allowed_documents:
            raise ValueError("no searchable documents are available")

        search = PersianHybridSearch(
            qdrant_client=qdrant,
            chunk_fetcher=chunk_fetcher_factory(database),
            chunk_revision_fetcher=chunk_revision_fetcher_factory(database),
            tei_embed_url=os.getenv("TEI_EMBED_URL"),
            tei_rerank_url=os.getenv("TEI_RERANK_URL"),
            http_client=async_http,
            sync_http_client=sync_http,
            blocking_runner=blocking,
        )
        original_embed_query = search.embedding_client.embed_query
        runs: list[dict[str, Any]] = []
        for run_index in range(1, run_count + 1):
            captured_embeddings: list[list[float]] = []

            async def capture_embedding(query: str) -> list[float]:
                vector = await original_embed_query(query)
                captured_embeddings.append(vector)
                return vector

            search.embedding_client.embed_query = capture_embedding
            hybrid = await search.search(
                canonical_query,
                top_k=retrieval_top_k,
                allowed_docs=allowed_documents,
            )
            if len(captured_embeddings) != 1:
                raise RuntimeError(
                    "expected exactly one query embedding during retrieval"
                )
            reranked = await search.rerank_search_results(
                canonical_query,
                hybrid,
                top_k=rerank_top_k,
            )
            selected = reranked[:rerank_top_k]
            embedding = captured_embeddings[0]
            embedding_signature = vector_float32_le_signature(embedding)
            embedding_norm = math.sqrt(math.fsum(
                float(value) * float(value) for value in embedding
            ))
            runs.append({
                "run": run_index,
                "embedding": {
                    **embedding_signature,
                    "norm": _score(embedding_norm),
                },
                "hybrid_top": _hybrid_records(hybrid),
                "rerank_top": _rerank_records(selected),
            })

        stability = analyze_runs(runs)
        return {
            "schema_version": SCHEMA_VERSION,
            "generation": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            "query": {
                "raw_query_fingerprint": query_fingerprint(raw_query),
                "normalized_query_fingerprint": query_fingerprint(
                    normalized_query
                ),
                "canonical_retrieval_query_fingerprint": query_fingerprint(
                    canonical_query
                ),
                "canonical_retrieval_query": canonical_query,
            },
            "configuration": {
                "runs": run_count,
                "retrieval_top_k": retrieval_top_k,
                "rerank_top_k": rerank_top_k,
                "document_count": len(allowed_documents),
                "query_canonicalization_enabled": (
                    PERFORMANCE_SETTINGS.rag_query_canonicalization_enabled
                ),
                "alias_artifact_basename": RETRIEVAL_QUERY_ALIASES_PATH.name,
                "alias_schema_version": RETRIEVAL_QUERY_ALIASES_SCHEMA_VERSION,
                "alias_artifact_sha256": RETRIEVAL_QUERY_ALIASES_SHA256,
                "query_embedding_role": "retrieval_query",
                "query_embedding_prompt_name": "query",
                "query_embedding_normalize": True,
                "vector_hash_representation": (
                    "SHA256 over values converted one-by-one to IEEE-754 "
                    "float32 little-endian bytes"
                ),
                "score_exact_representation": "IEEE-754 float64 little-endian hex",
                "sequential": True,
                "cache_cleared_between_runs": False,
            },
            "runs": runs,
            "stability": stability,
        }
    finally:
        if search is not None:
            await search.aclose()
        await async_http.aclose()
        sync_http.close()
        qdrant.close()
        await blocking.aclose()


def _print_summary(report: dict[str, Any], output: Path) -> None:
    stability = report["stability"]
    drift = stability["drift"]
    print(f"OUTPUT={output}")
    print(f"RUNS_COMPLETED={len(report['runs'])}")
    for key in (
        "QUERY_EMBEDDING_EXACT_STABLE",
        "HYBRID_TOP50_ID_ORDER_STABLE",
        "HYBRID_TOP50_CONTENT_STABLE",
        "HYBRID_TOP50_SCORES_EXACT_STABLE",
        "RERANK_TOP10_ID_ORDER_STABLE",
        "RERANK_TOP10_CONTENT_STABLE",
        "RERANK_SCORES_EXACT_STABLE",
        "OVERALL_EXACT_STABLE",
    ):
        print(f"{key}={str(stability[key]).lower()}")
    print(
        "MAX_SEMANTIC_SCORE_DRIFT="
        f"{drift['maximum_absolute_semantic_score_difference']!r}"
    )
    print(
        "MAX_BM25_SCORE_DRIFT="
        f"{drift['maximum_absolute_bm25_score_difference']!r}"
    )
    print(
        "MAX_HYBRID_SCORE_DRIFT="
        f"{drift['maximum_absolute_hybrid_score_difference']!r}"
    )
    print(
        "MAX_RERANKER_SCORE_DRIFT="
        f"{drift['maximum_absolute_reranker_score_difference']!r}"
    )
    print(f"FIRST_UNSTABLE_STAGE={stability['FIRST_UNSTABLE_STAGE']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the real RagBot retrieval and BGE rerank path sequentially. "
            "Exit codes: 0=exactly stable, 1=instability, "
            "2=execution/configuration error."
        )
    )
    parser.add_argument("--query", required=True)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument(
        "--retrieval-top-k",
        type=int,
        default=PERFORMANCE_SETTINGS.rag_retrieval_top_k,
    )
    parser.add_argument(
        "--rerank-top-k",
        type=int,
        default=PERFORMANCE_SETTINGS.rag_context_rerank_top_k,
    )
    parser.add_argument(
        "--document",
        action="append",
        help="limit to an available document title; repeat for multiple",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


async def _async_main(args: argparse.Namespace) -> int:
    report = await run_stability(
        raw_query=args.query,
        run_count=args.runs,
        retrieval_top_k=args.retrieval_top_k,
        rerank_top_k=args.rerank_top_k,
        documents=args.document,
    )
    write_json_report(args.output, report)
    _print_summary(report, args.output)
    return 0 if report["stability"]["OVERALL_EXACT_STABLE"] else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_async_main(args))
    except Exception as exc:
        print(f"ERROR={type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
