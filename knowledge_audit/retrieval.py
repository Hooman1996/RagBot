"""Actual production selection and request-local audit retrieval, no answers."""
from __future__ import annotations
import asyncio
import time

from document_category import get_document_category
from knowledge_audit.privacy import AuditError
from knowledge_audit.snapshot import assert_compatible
from pipeline_observer import bind_pipeline_observer
from utils.concurrency import run_with_limit
from utils.performance_config import PERFORMANCE_SETTINGS
from utils.read_only_audit import text_sha256
from utils.audit_dispatch import audit_dispatch


class AuditRetrieval:
    def __init__(self, rag, snapshot, runner, signature_provider, *, limiter=None,
                 initial_depth=150, broader_depth=300, initial_entries=50):
        self.rag, self.snapshot, self.runner = rag, snapshot, runner
        self.initial_depth, self.broader_depth, self.initial_entries = initial_depth, broader_depth, initial_entries
        self.signature_provider, self.limiter = signature_provider, limiter
        self.allowed_documents = sorted({r["document_title"] for r in snapshot["records"]})
        self.records = {r["chunk_id"]: r for r in snapshot["records"]}
        self.metrics = []

    async def check(self):
        current = await audit_dispatch('source_check',lambda:self.runner.run(self.signature_provider, 'a2-drift-check'))
        assert_compatible(self.snapshot["source_signature"], current)

    async def fetch(self, query, *, production=False, depth=None, documents=None):
        depth = self.initial_depth if depth is None else depth
        docs = documents or self.allowed_documents
        if not docs or not set(docs) <= set(self.allowed_documents):
            raise AuditError("invalid_snapshot_scope")
        before = time.perf_counter()
        await self.check()
        async def operation():
            with bind_pipeline_observer(None):
                if production:
                    candidates = await self.rag.retrieve(query, top_k=PERFORMANCE_SETTINGS.rag_retrieval_top_k, allowed_docs=docs)
                    ordered = await self.rag.search_engine.rerank_search_results(query, candidates,
                        top_k=PERFORMANCE_SETTINGS.rag_context_rerank_top_k) if PERFORMANCE_SETTINGS.rag_context_rerank_enabled else candidates
                    selected = ordered if get_document_category(docs[0]) == "FAQ" else ordered[:3]
                else:
                    if depth not in {self.initial_depth, self.broader_depth}:
                        raise AuditError("invalid_audit_depth")
                    candidates = await self.rag.retrieve(query, top_k=depth, allowed_docs=docs,
                        bm25_candidate_limit=depth, semantic_candidate_limit=depth)
                    # Every candidate is scored by unchanged question/taxonomy
                    # rerank text. One global selection, no answer-aware scoring.
                    ordered = await self.rag.search_engine.rerank_search_results(query, candidates,
                        top_k=len(candidates)) if candidates else []
                    selected = ordered[:self.initial_entries] if depth == self.initial_depth else ordered
                return candidates, selected
        candidates, selected = await asyncio.wait_for(run_with_limit(self.limiter, operation,
            acquire_timeout=PERFORMANCE_SETTINGS.request_admission_timeout_seconds) if self.limiter else operation(),
            PERFORMANCE_SETTINGS.application_request_timeout_seconds)
        await self.check()
        for candidate in candidates:
            cid = str(candidate.doc_id)
            if cid not in self.records or text_sha256(candidate.content) != self.records[cid]["source_content_sha256"]:
                raise AuditError("candidate_snapshot_mismatch")
        ids = [str(c.doc_id) for c in selected]
        if len(set(ids)) != len(ids):
            raise AuditError("duplicate_candidate_identity")
        metric = {"purpose": "production_baseline" if production else "initial_audit" if depth == self.initial_depth else "broader_audit",
                  "candidate_count": len(candidates), "candidate_ids": [str(c.doc_id) for c in candidates],
                  "selected_ids": ids, "depths": [PERFORMANCE_SETTINGS.rag_bm25_candidate_limit,
                      PERFORMANCE_SETTINGS.rag_semantic_candidate_limit, PERFORMANCE_SETTINGS.rag_retrieval_top_k] if production else [depth] * 3,
                  "duration_ms": round((time.perf_counter() - before) * 1000, 3)}
        self.metrics.append(metric)
        return metric
