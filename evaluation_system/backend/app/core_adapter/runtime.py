"""Side-effect-free construction of the canonical RagBot turn executor."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager

import httpx
from openai import AsyncOpenAI
from qdrant_client import QdrantClient

from agent_service import AgentService
from answering_service import AnsweringService
from document_category import get_document_category
from intent_classifier import IntentClassifier
from new_architecture.app.services.history.database import DatabaseManager
from new_architecture.app.services.history.rewriting import HistoryRewritingService
from utils.RagSystem import RAGSystem
from utils.client_lifecycle import SerializedClient
from utils.concurrency import BoundedBlockingRunner
from utils.performance_config import PERFORMANCE_SETTINGS
from utils.persian_hybrid_search import PersianTextProcessor
from utils.rag_utils import chunk_fetcher_factory, chunk_revision_fetcher_factory


class _ExplicitEvaluationHistoryRequired:
    namespace = "evaluation-explicit-provider-required"

    def lock_key(self, conversation_key):
        raise RuntimeError("evaluation history provider was not supplied")

    async def load_rewrite_messages(self, conversation_key):
        raise RuntimeError("evaluation history provider was not supplied")

    async def load_snapshot(self, conversation_key):
        raise RuntimeError("evaluation history provider was not supplied")

    async def save_snapshot(self, snapshot, final_state):
        raise RuntimeError("evaluation history provider was not supplied")


@asynccontextmanager
async def canonical_turn_runtime():
    """Build existing core classes without application DB/schema/MinIO mutation."""

    blocking = BoundedBlockingRunner(PERFORMANCE_SETTINGS.blocking_concurrency_limit)
    db = DatabaseManager(
        host=os.getenv("POSTGRES_HOST"), port=os.getenv("POSTGRES_PORT"),
        dbname=os.getenv("POSTGRES_DB"), user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )
    qdrant = SerializedClient(QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
        api_key=os.getenv("QDRANT_API_KEY"),
        https=os.getenv("QDRANT_HTTPS", "false").lower() == "true",
        timeout=10.0,
    ))
    tei_timeout = httpx.Timeout(
        connect=PERFORMANCE_SETTINGS.tei_http_connect_timeout_seconds,
        read=PERFORMANCE_SETTINGS.tei_http_read_timeout_seconds,
        write=PERFORMANCE_SETTINGS.tei_http_write_timeout_seconds,
        pool=PERFORMANCE_SETTINGS.tei_http_pool_timeout_seconds,
    )
    tei_limits = httpx.Limits(
        max_connections=PERFORMANCE_SETTINGS.tei_http_max_connections,
        max_keepalive_connections=PERFORMANCE_SETTINGS.tei_http_max_keepalive_connections,
        keepalive_expiry=PERFORMANCE_SETTINGS.tei_http_keepalive_expiry_seconds,
    )
    tei_async = httpx.AsyncClient(timeout=tei_timeout, limits=tei_limits)
    tei_sync = httpx.Client(timeout=tei_timeout, limits=tei_limits)
    vllm_http = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=PERFORMANCE_SETTINGS.vllm_http_connect_timeout_seconds,
            read=PERFORMANCE_SETTINGS.vllm_http_read_timeout_seconds,
            write=PERFORMANCE_SETTINGS.vllm_http_write_timeout_seconds,
            pool=PERFORMANCE_SETTINGS.vllm_http_pool_timeout_seconds,
        ),
        limits=httpx.Limits(
            max_connections=PERFORMANCE_SETTINGS.vllm_http_max_connections,
            max_keepalive_connections=PERFORMANCE_SETTINGS.vllm_http_max_keepalive_connections,
            keepalive_expiry=PERFORMANCE_SETTINGS.vllm_http_keepalive_expiry_seconds,
        ),
    )
    llm = AsyncOpenAI(
        base_url=os.getenv("VLLM_URL", "http://localhost:8000/v1"),
        api_key="vllm-token-not-needed", max_retries=0, http_client=vllm_http,
    )
    rag = None
    try:
        processor = await blocking.run(PersianTextProcessor, use_stemming=False)
        rag = await blocking.run(
            RAGSystem,
            qdrant_client=qdrant,
            chunk_fetcher=chunk_fetcher_factory(db),
            chunk_revision_fetcher=chunk_revision_fetcher_factory(db),
            llm_client=llm,
            tei_http_client=tei_async,
            tei_sync_http_client=tei_sync,
            blocking_runner=blocking,
        )
        with open("scenarios.json", "r", encoding="utf-8") as stream:
            scenarios = {item["id"]: item for item in json.load(stream)["scenarios"]}
        classifier = await blocking.run(
            IntentClassifier,
            embedding_model=rag.search_engine._encode_query,
            scenarios_path="scenarios.json",
            blocking_runner=blocking,
        )
        agent = AgentService(
            rag_system=rag, intent_classifier=classifier, scenarios_db=scenarios,
            db_manager=db, chat_manager=None, blocking_runner=blocking,
            category_resolver=get_document_category,
            history_provider=_ExplicitEvaluationHistoryRequired(),
        )
        rewriter = HistoryRewritingService(rag, db)
        yield AnsweringService(
            agent_service=agent,
            intent_classifier=classifier,
            history_rewriting_service=rewriter,
            text_processor=processor,
            blocking_runner=blocking,
            category_resolver=get_document_category,
            selection_validator=db.filter_available_document_titles,
            history_provider=agent.history_provider,
        )
    finally:
        if rag is not None:
            await rag.aclose()
        await tei_async.aclose()
        tei_sync.close()
        await llm.close()
        await vllm_http.aclose()
        qdrant.close()
        await blocking.aclose()
