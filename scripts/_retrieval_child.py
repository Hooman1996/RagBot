#!/usr/bin/env python3
"""Child of `retrieval_eval.py run`, executed with cwd and PYTHONPATH set to a
configuration worktree.

It imports the standard library, the worktree's own modules and the client
libraries the worktree's main.py uses (httpx, openai), never this checkout's
code. It writes private files only into the run directory the parent created,
and records a failing case by its exception class name alone.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
import logging
import os
from pathlib import Path
import re
import time

TITLE = re.compile(r'question\s*:\s*(.+?)(?=answer\s*\d*\s*:|question category\s*:|$)', re.DOTALL)


def private_json(path: Path, payload) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
        stream.write("\n")


def faq_title(content: str) -> str:
    """The FAQ question field, parsed as agent_graph.prepare_context does."""
    match = TITLE.search(content or "")
    return match.group(1).strip() if match else ""


async def select_context(rag, query, documents, *, settings, category_of):
    """Production selection from agent_graph.make_handle_general."""
    retrieved = await rag.retrieve(query, top_k=settings.rag_retrieval_top_k, allowed_docs=documents)
    if settings.rag_context_rerank_enabled:
        reranked = await rag.search_engine.rerank_search_results(
            query, retrieved, top_k=settings.rag_context_rerank_top_k)
    else:
        reranked = None
    ordered = retrieved if reranked is None else reranked
    context = ordered if category_of(documents[0]) == "FAQ" else ordered[:3]
    return retrieved, reranked, context


async def evaluate(rag, cases, documents, *, settings, category_of, observer=None):
    per_question, titles, errors = [], {}, 0
    for case in cases:
        start = time.perf_counter()
        try:
            if observer is None:
                retrieved, reranked, context = await select_context(
                    rag, case["retrieval_query"], documents, settings=settings, category_of=category_of)
            else:
                with observer(None):
                    retrieved, reranked, context = await select_context(
                        rag, case["retrieval_query"], documents, settings=settings, category_of=category_of)
        except Exception as exc:
            errors += 1
            per_question.append({"question_id": case["question_id"], "error": type(exc).__name__})
            continue
        latency_ms = round((time.perf_counter() - start) * 1000, 3)
        for result in (*retrieved, *(reranked or ()), *context):
            titles.setdefault(str(result.doc_id), faq_title(result.content))
        per_question.append({
            "question_id": case["question_id"],
            "retrieved_ids": [str(r.doc_id) for r in retrieved],
            "reranked_ids": None if reranked is None else [str(r.doc_id) for r in reranked],
            "context_ids": [str(r.doc_id) for r in context],
            "empty": not context,
            "latency_ms": latency_ms,
            "error": None,
        })
    return per_question, titles, errors


async def live(request: dict, run_dir: Path) -> None:
    import httpx
    from openai import AsyncOpenAI
    from document_category import get_document_category
    from new_architecture.app.services.db_connection import DatabaseConnections
    from new_architecture.app.services.history.database import DatabaseManager
    from pipeline_observer import bind_pipeline_observer
    from utils.RagSystem import RAGSystem
    from utils.client_lifecycle import SerializedClient
    from utils.concurrency import BoundedBlockingRunner
    from utils.performance_config import PERFORMANCE_SETTINGS as ps
    from utils.rag_utils import chunk_fetcher_factory, chunk_revision_fetcher_factory

    settings = {k: v for k, v in asdict(ps).items() if k.startswith(("rag_", "tei_rerank_"))}
    cases = json.loads(Path(request["cases_file"]).read_text(encoding="utf-8"))["cases"]
    # As main.py lifespan, minus init_db, authentication, OCR, the intent
    # classifier and the agent services.
    runner = BoundedBlockingRunner(ps.blocking_concurrency_limit)
    db_manager = DatabaseManager(host=os.getenv("POSTGRES_HOST"), port=os.getenv("POSTGRES_PORT"),
                                 dbname=os.getenv("POSTGRES_DB"), user=os.getenv("POSTGRES_USER"),
                                 password=os.getenv("POSTGRES_PASSWORD"))
    connections = DatabaseConnections()
    rag = tei = tei_sync = llm = None
    try:
        if not await runner.run(connections.connect_all, wait_for_completion_on_cancel=True):
            raise RuntimeError("connect_all_failed")
        connections.qdrant_client = SerializedClient(connections.qdrant_client)
        tei_timeout = httpx.Timeout(connect=ps.tei_http_connect_timeout_seconds, read=ps.tei_http_read_timeout_seconds,
                                    write=ps.tei_http_write_timeout_seconds, pool=ps.tei_http_pool_timeout_seconds)
        tei_limits = httpx.Limits(max_connections=ps.tei_http_max_connections,
                                  max_keepalive_connections=ps.tei_http_max_keepalive_connections,
                                  keepalive_expiry=ps.tei_http_keepalive_expiry_seconds)
        tei = httpx.AsyncClient(timeout=tei_timeout, limits=tei_limits)
        tei_sync = httpx.Client(timeout=tei_timeout, limits=tei_limits)
        vllm_timeout = httpx.Timeout(connect=ps.vllm_http_connect_timeout_seconds, read=ps.vllm_http_read_timeout_seconds,
                                     write=ps.vllm_http_write_timeout_seconds, pool=ps.vllm_http_pool_timeout_seconds)
        llm = AsyncOpenAI(
            base_url=os.getenv("VLLM_URL", "http://localhost:8000/v1"), api_key="vllm-token-not-needed",
            timeout=vllm_timeout, max_retries=0,
            http_client=httpx.AsyncClient(timeout=vllm_timeout, limits=httpx.Limits(
                max_connections=ps.vllm_http_max_connections,
                max_keepalive_connections=ps.vllm_http_max_keepalive_connections,
                keepalive_expiry=ps.vllm_http_keepalive_expiry_seconds)))
        rag = await runner.run(RAGSystem, qdrant_client=connections.qdrant_client,
                               chunk_fetcher=chunk_fetcher_factory(db_manager),
                               chunk_revision_fetcher=chunk_revision_fetcher_factory(db_manager),
                               llm_client=llm, tei_http_client=tei, tei_sync_http_client=tei_sync,
                               blocking_runner=runner)
        per_question, titles, errors = await evaluate(rag, cases, request["documents"], settings=ps,
            category_of=get_document_category, observer=bind_pipeline_observer)
        private_json(run_dir / "per_question.json", per_question)
        private_json(run_dir / "titles.json", titles)
        private_json(run_dir / "child.json", {"settings": settings, "case_count": len(cases),
                                              "error_count": errors, "fatal": None})
    finally:
        for close in ((rag and rag.aclose), (llm and llm.close), (tei and tei.aclose)):
            if close:
                try:
                    await close()
                except Exception:
                    pass
        for close in ((tei_sync and tei_sync.close), connections.close_all):
            if close:
                try:
                    await runner.run(close, wait_for_completion_on_cancel=True)
                except Exception:
                    pass
        await runner.aclose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    run_dir = parser.parse_args().run_dir
    logging.disable(logging.CRITICAL)
    try:
        request = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
        asyncio.run(live(request, run_dir))
    except BaseException as exc:
        if not (run_dir / "child.json").exists():
            private_json(run_dir / "child.json", {"fatal": type(exc).__name__})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
