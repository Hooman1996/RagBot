"""Local service wiring and admission; never use startup/init or answering graph."""
from __future__ import annotations
import asyncio
import os

from knowledge_audit.model import AuditModel
from knowledge_audit.preparation import QueryPreparer
from knowledge_audit.pipeline import CoverageEvaluator
from knowledge_audit.retrieval import AuditRetrieval
from knowledge_audit.runtime import confirm_staging
from utils.concurrency import run_with_limit
from utils.performance_config import PERFORMANCE_SETTINGS


class AdmittedPreparer:
    def __init__(self, preparer, limiter):
        self.preparer, self.limiter = preparer, limiter
    async def prepare(self, *args, **kwargs):
        return await asyncio.wait_for(run_with_limit(self.limiter, lambda: self.preparer.prepare(*args, **kwargs),
            acquire_timeout=PERFORMANCE_SETTINGS.request_admission_timeout_seconds), PERFORMANCE_SETTINGS.application_request_timeout_seconds)


async def build_engine(store, meta, settings, *, answering, runner, limiter):
    import httpx
    from scripts.kb_signature import create_signature
    confirm_staging(confirmed=True, model=True, snapshot=True)
    # Confirm the reranker too; it was not needed by A1's preparation guard.
    from dotenv import dotenv_values
    from knowledge_audit.runtime import ROOT
    from urllib.parse import urlsplit
    target = os.environ.get("TEI_RERANK_URL", "")
    if target != dotenv_values(ROOT / ".env").get("TEI_RERANK_URL") or urlsplit(target).hostname not in {"localhost", "127.0.0.1", "::1"}:
        from knowledge_audit.privacy import AuditError
        raise AuditError("unconfirmed_service_target")
    dataset, redactor = await runner.run(store.dataset, meta["dataset_id"], meta["owner_id"])
    snapshot = await runner.run(store.snapshot, meta["snapshot_id"], meta["owner_id"])
    rag = answering.agent_service.rag_system
    http = httpx.AsyncClient(timeout=PERFORMANCE_SETTINGS.vllm_http_read_timeout_seconds)
    try:
        model = AuditModel(rag, http, os.environ["VLLM_URL"], settings, redactor, limiter=limiter)
        await model.discover()
        model.metrics_path = store._path("runs", meta["run_id"]) / "model-metrics.jsonl"
        retrieval = AuditRetrieval(rag, snapshot, runner, create_signature, limiter=limiter)
        await retrieval.check()
        preparer = AdmittedPreparer(QueryPreparer.from_answering_service(answering), limiter)
        engine = CoverageEvaluator(snapshot=snapshot, model=model, retrieval=retrieval, preparer=preparer,
            redactor=redactor, dataset=dataset, entry_budget=meta["settings"]["entry_budget"],
            documents=meta["settings"].get("documents"))
        from knowledge_audit.runtime import configuration_identity
        preparation_config = configuration_identity(dataset.timestamp_policy, len(meta["selected_row_ids"]), redactor)
        preparation_config["model_sample_rule"] = meta["settings"].get("selection_method", "explicit_source_row_ids")
        engine.runtime_configuration = preparation_config
        engine.aclose = http.aclose
        return engine
    except BaseException:
        await http.aclose()
        raise


async def standalone_components(runner):
    from qdrant_client import QdrantClient
    from utils.client_lifecycle import SerializedClient
    from utils.RagSystem import RAGSystem
    from utils.rag_utils import chunk_fetcher_factory, chunk_revision_fetcher_factory
    from utils.persian_hybrid_search import PersianTextProcessor
    from new_architecture.app.services.history.database import DatabaseManager
    from new_architecture.app.services.history.rewriting import HistoryRewritingService
    from intent_classifier_factory import build_intent_classifier
    from types import SimpleNamespace
    db = DatabaseManager()
    vector = SerializedClient(QdrantClient(host=os.environ["QDRANT_HOST"], port=int(os.environ["QDRANT_PORT"]),
        api_key=os.environ.get("QDRANT_API_KEY"), https=os.environ.get("QDRANT_HTTPS", "false").lower() == "true"))
    rag = await runner.run(RAGSystem, qdrant_client=vector, chunk_fetcher=chunk_fetcher_factory(db),
                           chunk_revision_fetcher=chunk_revision_fetcher_factory(db), blocking_runner=runner)
    try:
        processor = await runner.run(PersianTextProcessor, use_stemming=False)
        classifier = await runner.run(build_intent_classifier, embedding_model=rag.search_engine._encode_query,
                                     blocking_runner=runner)
        answering = SimpleNamespace(text_processor=processor, intent_classifier=classifier,
            history_rewriting_service=HistoryRewritingService(rag, None), blocking_runner=runner,
            agent_service=SimpleNamespace(rag_system=rag))
        async def close():
            await rag.aclose()
            await runner.run(vector.close)
        return answering, close
    except BaseException:
        await rag.aclose()
        await runner.run(vector.close)
        raise
