#!/usr/bin/env python3
"""Offline P0 observations of current code; no env loading, network, or writes.

AST-extract only the named production methods to avoid heavyweight imports and
startup side effects. Dependencies and scores are synthetic. Exit 0 means the
diagnostic completed, NOT that observed defects or retrieval quality passed.
"""
from __future__ import annotations

import ast
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def source(path):
    return ast.parse((ROOT / path).read_text(encoding="utf-8"))


def execute(nodes, namespace):
    module = ast.Module(body=[ast.ImportFrom(
        module="__future__", names=[ast.alias(name="annotations")], level=0
    ), *(n for n in nodes if not (
        isinstance(n, ast.ImportFrom) and n.module == "__future__"
    ))], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), "<P0 source extraction>", "exec"), namespace)


@asynccontextmanager
async def span(*args):
    yield


class ImmediateRunner:
    async def run(self, function, *args):
        return function(*args)


class FakeHttp:
    def __init__(self, maximum=None):
        self.maximum = maximum
        self.sizes = []

    async def post(self, url, json):
        size = len(json["texts"])
        self.sizes.append(size)
        if self.maximum is not None and size > self.maximum:
            raise RuntimeError("synthetic_server_batch_limit")
        # Deliberately reverse response indexes and tie scores.
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: [
            {"index": i, "score": 0.5} for i in reversed(range(size))
        ])


async def observations():
    tree = source("utils/persian_hybrid_search.py")
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    methods = {"search", "_score_bm25", "rerank_search_results", "_ensure_open"}
    hybrid = ast.ClassDef(name="ExtractedSearch", bases=[], keywords=[], body=[
        n for n in classes["PersianHybridSearch"].body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in methods
    ], decorator_list=[])
    if len(hybrid.body) != len(methods):
        raise RuntimeError("production_method_contract_changed")
    namespace = dict(globals(), current_trace=lambda: None, trace_span=span,
                     emit_pipeline_stage_lazy=lambda factory: None,
                     normalize_persian_text=lambda value: value,
                     build_faq_rerank_text=lambda value: "synthetic title",
                     httpx=SimpleNamespace(PoolTimeout=TimeoutError,
                         TimeoutException=TimeoutError, HTTPError=OSError),
                     ServiceTimeoutError=RuntimeError,
                     ServiceUnavailableError=RuntimeError,
                     ServiceProtocolError=RuntimeError)
    settings_tree = source("utils/performance_config.py")
    settings_namespace = dict(globals())
    execute([n for n in settings_tree.body if not (
        isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in
        {"PERFORMANCE_SETTINGS", "PIPELINE_DEBUG_SETTINGS"} for t in n.targets)
    )], settings_namespace)
    load = settings_namespace["load_performance_settings"]
    with patch.dict(os.environ, {}, clear=True):
        defaults = load()
    namespace["PERFORMANCE_SETTINGS"] = defaults
    namespace["validate_retrieval_depth"] = settings_namespace["validate_retrieval_depth"]
    execute([classes["SearchResult"], hybrid], namespace)
    search = namespace["ExtractedSearch"]()
    search._blocking_runner = ImmediateRunner()
    # 120 positive sparse hits; default 50 dense hits; 50 overlaps.
    ids = [f"fixture-{i:03}" for i in range(1, 171)]
    chunks = {i: {"text": "synthetic content", "document_name": "fixture"} for i in ids}
    bm25 = SimpleNamespace(get_scores=lambda tokens: [float(120-i) for i in range(120)])
    search._get_or_build_bm25 = lambda docs: (bm25, ids[:120], chunks)
    search._process_query = lambda query: ["fixture"]
    search._normalise_query = lambda query: query
    dense_limits = []

    async def dense(query, docs, top_k):
        dense_limits.append(top_k)
        return {i: 0.5 for i in ids[:top_k]}

    search._semantic_search = dense
    started = time.perf_counter()
    first = await search.search("synthetic", allowed_docs=["fixture"])
    second = await search.search("synthetic", allowed_docs=["fixture"])
    search._http = FakeHttp()
    search.tei_rerank_url = "synthetic://no-network"
    selected = await search.rerank_search_results("synthetic", first, top_k=defaults.rag_context_rerank_top_k)
    elapsed_ms = (time.perf_counter() - started) * 1000
    default_rerank_sizes = list(search._http.sizes)
    _, sparse = search._score_bm25(bm25, ids[:120], ["fixture"])
    _, expanded_sparse = search._score_bm25(bm25, ids[:120], ["fixture"], 150)
    search._get_or_build_bm25 = lambda docs: (
        SimpleNamespace(get_scores=lambda tokens: [1.0]), [ids[0]], chunks
    )

    async def disjoint_dense(query, docs, top_k):
        return {ids[1]: 0.5}

    search._semantic_search = disjoint_dense
    disjoint = await search.search("synthetic", top_k=2, allowed_docs=["fixture"])
    validation = []
    for overrides in [
        {"RAG_RETRIEVAL_TOP_K": "150"},
        {"RAG_RETRIEVAL_TOP_K": "150", "RAG_SEMANTIC_CANDIDATE_LIMIT": "150", "RAG_CONTEXT_RERANK_TOP_K": "50"},
        {"RAG_RETRIEVAL_TOP_K": "300", "RAG_SEMANTIC_CANDIDATE_LIMIT": "300", "RAG_CONTEXT_RERANK_TOP_K": "50"},
    ]:
        with patch.dict(os.environ, overrides, clear=True):
            try:
                load()
                outcome = "accepted"
            except ValueError:
                outcome = "rejected"
        validation.append({"keys": sorted(overrides), "outcome": outcome})
    # Synthetic boundary follows the verified P0.1 staging client limit.
    search._http = FakeHttp(maximum=64)
    candidates = [namespace["SearchResult"](
        doc_id=i, content="synthetic", score=0.1, bm25_score=1.0,
        semantic_score=0.5, original_rrf_rank=rank
    ) for rank, i in enumerate(ids[:150], 1)]
    try:
        await search.rerank_search_results("synthetic", candidates, top_k=50)
        batch_outcome = "accepted"
    except RuntimeError:
        batch_outcome = "synthetic_server_batch_limit"
    kb = source("kb_manager.py")
    functions = {n.name: n for n in kb.body if isinstance(n, ast.FunctionDef)}
    execute([functions["extract_qa_components"]], namespace)
    content = "question: synthetic\nanswer: synthetic\nquestion category: fixture. sub_category: fixture"
    parsed = namespace["extract_qa_components"](content)
    round_trips = {}
    for name in ["api_create_chunk", "api_sync_chunk"]:
        reconstruction = next(n for n in ast.walk(functions[name])
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name)
                and t.id == "reconstructed_content" for t in n.targets)
            and isinstance(n.value, ast.JoinedStr))
        for mode, answer in [("clean_fields", "synthetic"), ("editor_parsed", parsed["answer"])]:
            scope = dict(namespace, payload=SimpleNamespace(question="synthetic", answer=answer),
                         question="synthetic", answer=answer)
            execute([reconstruction], scope)
            round_trips[f"{name}:{mode}"] = "question category:" in scope["reconstructed_content"]
    return {
        "fixture_only": True, "network_calls": 0, "env_files_loaded": 0,
        "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
            ["utils/persian_hybrid_search.py", "utils/performance_config.py", "kb_manager.py"]},
        "production_source_defaults": {"retrieval": defaults.rag_retrieval_top_k,
            "bm25_limit": defaults.rag_bm25_candidate_limit,
            "dense_limit": defaults.rag_semantic_candidate_limit,
            "context_rerank": defaults.rag_context_rerank_top_k},
        "sparse": {"positive_fixture_scores": 120, "returned_count": len(sparse),
            "expanded_limit": 150, "expanded_returned_count": len(expanded_sparse),
            "bm25_cap_configurable": len(expanded_sparse) == 120},
        "rrf": {"historical_missing_rank_contribution": 1/(60+61),
            "actual_disjoint_scores": {r.doc_id: r.score for r in disjoint},
            "single_rank1_expected_unrounded": 1/(60+1),
            "missing_branch_defect_resolved": all(
                r.score == round(1/(60+1), 6) for r in disjoint
            )},
        "baseline": {"candidate_count": len(first), "candidate_ids": [r.doc_id for r in first],
            "selected_context_ids": [r.doc_id for r in selected],
            "repeated_order_equal": [r.doc_id for r in first] == [r.doc_id for r in second],
            "dense_request_limits": dense_limits, "reranker_request_sizes": default_rerank_sizes,
            "synthetic_elapsed_ms": round(elapsed_ms, 3)},
        "audit_rerank": {"request_sizes": search._http.sizes, "outcome": batch_outcome,
            "one_request_batching_still_outstanding": search._http.sizes == [150],
            "synthetic_server_batch_limit": 64,
            "server_limit_is_synthetic": True},
        "depth_validation": validation,
        "taxonomy_marker_retained": round_trips,
        "revert": {"uses_stored_content_directly": any(isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "target_content" for t in n.targets)
            and ast.unparse(n.value) == "str(version_rec['content'])"
            for n in ast.walk(functions["api_revert_chunk"]))},
    }


if __name__ == "__main__":
    try:
        print(json.dumps(asyncio.run(observations()), indent=2, sort_keys=True))
    except Exception as exc:
        print(f"P0_DIAGNOSTIC_ERROR={type(exc).__name__}", file=sys.stderr)
        sys.exit(2)
