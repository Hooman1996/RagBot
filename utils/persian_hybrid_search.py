import numpy as np
import asyncio
import math
import threading
import time
from typing import List, Dict, Tuple, Optional, Callable
from dataclasses import dataclass, replace
from tqdm import tqdm
import re

# Persian NLP - using parsivar
from parsivar import Normalizer, Tokenizer, FindStems

# Search
from rank_bm25 import BM25Okapi

# Qdrant for semantic search
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
import os

from dotenv import load_dotenv

# Load variables from .env into os.environ
load_dotenv()

import httpx
from utils.concurrency import BoundedBlockingRunner
from utils.performance_config import PERFORMANCE_SETTINGS
from utils.service_errors import (
    ServiceProtocolError,
    ServiceTimeoutError,
    ServiceUnavailableError,
)
from utils.request_instrumentation import current_trace, trace_span
from pipeline_observer import (
    PipelineStage,
    PipelineStageResult,
    emit_pipeline_stage_lazy,
)
from utils.tei_embedding_client import (
    TeiEmbeddingClient,
    build_document_payload,
    validate_embedding_response,
)
from utils.persian_normalization import normalize_persian_text
from utils.revision_cache import RevisionAwareCache

@dataclass
class SearchResult:
    """Search result container"""
    doc_id: str
    content: str
    score: float
    bm25_score: float
    semantic_score: float
    metadata: Optional[Dict] = None
    original_rrf_rank: int | None = None
    reranker_score: float | None = None
    reranker_rank: int | None = None


class PersianTextProcessor:
    """
    Handles all Persian text preprocessing using Parsivar
    """

    def __init__(self, use_stemming: bool = True):
        print("Initializing Persian text processor with Parsivar...")

        # Initialize Parsivar components
        self.normalizer = Normalizer()
        self.tokenizer = Tokenizer()
        self.stemmer = FindStems() if use_stemming else None
        self.use_stemming = use_stemming
        self._normalizer_lock = threading.Lock()

        # Persian stopwords list
        self.stopwords = self._load_stopwords()

        print(f"Loaded {len(self.stopwords)} Persian stopwords")

    def _load_stopwords(self) -> set:
        """Load Persian stopwords"""
        stopwords = {
            'و', 'در', 'به', 'از', 'که', 'این', 'را', 'با', 'برای', 'آن',
            'یک', 'شود', 'شده', 'خود', 'ها', 'می', 'یا', 'تا', 'اما', 'بر',
            'هم', 'نیز', 'گفت', 'دارد', 'کرد', 'کند', 'کنند', 'است', 'هست',
            'باشد', 'بود', 'داشت', 'داشته', 'شد', 'شده', 'بوده', 'های',
            'اند', 'ام', 'ای', 'ایم', 'اید', 'ات', 'اش', 'مان', 'تان', 'شان',
            'ی', 'یی', 'ها', 'تر', 'ترین', 'م', 'ت', 'ش',
            'چه', 'چی', 'کی', 'کجا', 'چرا', 'چگونه', 'چطور', 'چند', 'چنین',
            'الی', 'علی', 'عن', 'فی', 'ان', 'ال', 'ها', 'هایی', 'بسیار',
            'خیلی', 'همه', 'تمام', 'کل', 'هر', 'هیچ', 'بعضی', 'برخی', 'دیگر',
            'غیر', 'جز', 'فقط', 'حتی', 'ولی', 'لیکن', 'اگر', 'مگر', 'پس',
            'نه', 'بله', 'آری', 'بلی', 'چنانچه', 'زیرا', 'چون', 'وقتی', 'هنگامی',
            'همین', 'آنکه', 'اینکه', 'وی', 'او', 'ایشان', 'من', 'تو', 'ما', 'شما',
            'آنها', 'اینها', 'آنان', 'اینان', 'خویش', 'خویشتن'
        }
        return stopwords

    def normalize(self, text: str) -> str:
        if not text:
            return ""
        with self._normalizer_lock:
            text = self.normalizer.normalize(text)
        replacements = {
            'ك': 'ک', 'ي': 'ی', 'ى': 'ی',
            '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
            '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9',
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return re.sub(r'\s+', ' ', text).strip()

    def tokenize(self, text: str) -> List[str]:
        try:
            return self.tokenizer.tokenize_words(text)
        except Exception:
            return text.split()

    def stem(
        self,
        tokens: List[str],
        *,
        apply_document_overrides: bool = False,
    ) -> List[str]:
        if not self.use_stemming:
            return tokens

        stemmed = []

        # 1. Stop-Stem Dictionary: Words that end in م, ت, ش, ی but are root words
        do_not_strip = {
            'انگشت', 'کارت', 'ثبت', 'دست', 'پاسپورت', 'بلیت',
            'ساعت', 'قیمت', 'شرکت', 'شکایت', 'امنیت', 'هویت',
            'سایت', 'اکانت', 'فرمت', 'چت', 'ربات', 'کد', 'اینترنت'
        }

        # Preserve legacy BM25 document tokenization. Retrieval-query aliases
        # are applied only by retrieval_query_canonicalizer before search.
        document_token_overrides = {
            "انگشتم": "انگشت من",
            "رمزمو": "رمز من رو",
            "قسطمو": "قسط م رو",
            "واممو": "وام من رو",
            "حسابمو": "حساب من رو",
            "کارتش": "کارت اش رو",
        }

        noun_suffixes = [
            'هایم', 'هایت', 'هایش', 'هامون', 'هاتون', 'هاشون',
            'مان', 'تان', 'شان', 'ها', 'ام', 'ات', 'اش',
            'م', 'ت', 'ش', 'ی'
        ]

        for token in tokens:
            if apply_document_overrides and token in document_token_overrides:
                stemmed.append(document_token_overrides[token])
                continue

            # If it's a known root word, protect it
            if token in do_not_strip:
                stemmed.append(token)
                continue

            original_token = token

            # Try Parsivar's verb stemmer
            if self.stemmer is not None:
                try:
                    parsed = self.stemmer.convert_to_stem(token)
                    if parsed:
                        token = parsed
                except:
                    pass

            # Strip noun enclitics only if it wasn't modified and isn't protected
            if token == original_token and token not in do_not_strip:
                for suffix in noun_suffixes:
                    if token.endswith(suffix) and len(token) - len(suffix) >= 3:
                        candidate = token[:-len(suffix)]
                        # Extra safety: if stripping it creates a protected word, keep it
                        if candidate in do_not_strip:
                            token = candidate
                            break
                        token = candidate
                        break

            stemmed.append(token)

        return stemmed

    def remove_stopwords(self, tokens: List[str]) -> List[str]:
        return [token for token in tokens if token not in self.stopwords]

    def clean_tokens(self, tokens: List[str]) -> List[str]:
        cleaned = []
        for token in tokens:
            if len(token) < 2:
                continue
            if token.isdigit():
                continue
            if all(not c.isalnum() for c in token):
                continue
            cleaned.append(token)
        return cleaned

    def process(
        self,
        text: str,
        remove_stopwords: bool = True,
        apply_stemming: bool = True,
        apply_document_overrides: bool = False,
    ) -> List[str]:
        text = self.normalize(text)
        tokens = self.tokenize(text)
        if remove_stopwords:
            tokens = self.remove_stopwords(tokens)
        if apply_stemming and self.use_stemming:
            tokens = self.stem(
                tokens,
                apply_document_overrides=apply_document_overrides,
            )
        tokens = self.clean_tokens(tokens)
        return tokens

    def process_batch(self, texts: List[str], show_progress: bool = True) -> List[List[str]]:
        iterator = tqdm(texts, desc="Processing texts") if show_progress else texts
        return [self.process(text) for text in iterator]


# ------------------------------------------------------------------------------
# Main hybrid search – fully dynamic, no persistent indices
# ------------------------------------------------------------------------------
class PersianHybridSearch:
    """
    Hybrid search using BM25 (built on‑the‑fly) and Qdrant for semantic search.
    No chunk texts or vectors are stored in memory permanently.
    """

    def __init__(
        self,
        qdrant_client: QdrantClient,
        collection_name: str = os.getenv("QDRANT_COLLECTION"), #"hihelp_embeddings",
        query_embedding_model: str = os.getenv("EMBEDDING_MODEL"), #"/home/hooman/.cache/huggingface/hub/models--jinaai--jina-embeddings-v5-text-small-retrieval",
        use_gpu: bool = True,
        use_stemming: bool = True,
        chunk_fetcher: Optional[Callable[[List[str]], Dict[str, dict]]] = None,
        chunk_revision_fetcher: Optional[Callable[[List[str]], str]] = None,
        tei_embed_url = os.getenv("TEI_EMBED_URL"),
        tei_rerank_url = os.getenv("TEI_RERANK_URL"),
        http_client: Optional[httpx.AsyncClient] = None,
        sync_http_client: Optional[httpx.Client] = None,
        blocking_runner: Optional[BoundedBlockingRunner] = None,
        qdrant_concurrency: int | None = None,
    ):
        """
        Args:
            qdrant_client: connected QdrantClient instance
            collection_name: Qdrant collection name
            query_embedding_model: path to the Jina embeddings model (query only)
            use_gpu: load query model on GPU
            use_stemming: stemming for BM25 tokenisation
            chunk_fetcher: optional callable that takes a list of document titles
                           and returns a dict: chunk_id -> { "text": ..., "document_name": ..., ... }.
                           If not provided, the search will fail unless the chunk texts are
                           available in the Qdrant payload.
        """
        self.processor = PersianTextProcessor(use_stemming=use_stemming)
        self.qdrant_client = qdrant_client
        self.collection_name = collection_name

        if not isinstance(tei_embed_url, str) or not tei_embed_url.strip():
            raise ValueError("TEI_EMBED_URL must be present")
        self.tei_embed_url = tei_embed_url.rstrip("/")
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
        self._owns_http = http_client is None
        self._http = http_client or httpx.AsyncClient(
            timeout=timeout, limits=limits
        )
        self._owns_sync_http = sync_http_client is None
        self._sync_http = sync_http_client or httpx.Client(
            timeout=timeout, limits=limits
        )
        self.tei_rerank_url = tei_rerank_url.rstrip("/")
        self._bm25_cache: RevisionAwareCache[tuple, tuple] = (
            RevisionAwareCache()
        )
        self._processor_lock = threading.Lock()
        self._blocking_runner = blocking_runner or BoundedBlockingRunner()
        self._owns_blocking_runner = blocking_runner is None
        self._qdrant_semaphore = asyncio.Semaphore(
            qdrant_concurrency or PERFORMANCE_SETTINGS.qdrant_concurrency
        )
        self._qdrant_capacity = (
            qdrant_concurrency or PERFORMANCE_SETTINGS.qdrant_concurrency
        )
        self._qdrant_active = 0
        self._qdrant_waiting = 0
        self._qdrant_acquired_total = 0
        self._qdrant_released_total = 0
        self._tei_embedding_active = 0
        self._tei_reranker_active = 0
        self._tei_pool_timeout_total = 0
        self._closed = False
        self._expected_embedding_dimensions = int(
            os.getenv("QDRANT_VECTOR_SIZE", "1024")
        )
        self.embedding_client = TeiEmbeddingClient(
            self.tei_embed_url,
            self._http,
            expected_dimension=self._expected_embedding_dimensions,
        )
        
        self.chunk_fetcher = chunk_fetcher
        self.chunk_revision_fetcher = chunk_revision_fetcher


    async def _encode_query(self, query: str) -> list[float]:
        self._ensure_open()
        self._tei_embedding_active = getattr(
            self, "_tei_embedding_active", 0
        ) + 1
        try:
            async with trace_span("embedding"):
                return await self.embedding_client.embed_query(query)
        except httpx.PoolTimeout as exc:
            self._tei_pool_timeout_total = getattr(
                self, "_tei_pool_timeout_total", 0
            ) + 1
            raise ServiceTimeoutError("Embedding HTTP pool timed out") from exc
        except httpx.TimeoutException as exc:
            raise ServiceTimeoutError("Embedding service timed out") from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(
                "Embedding service is unavailable"
            ) from exc
        finally:
            self._tei_embedding_active -= 1

    def metrics_snapshot(self) -> dict[str, int]:
        return {
            "qdrant_capacity": getattr(self, "_qdrant_capacity", 0),
            "qdrant_active": getattr(self, "_qdrant_active", 0),
            "qdrant_waiting": getattr(self, "_qdrant_waiting", 0),
            "qdrant_acquired_total": getattr(self, "_qdrant_acquired_total", 0),
            "qdrant_released_total": getattr(self, "_qdrant_released_total", 0),
            "tei_embedding_active": getattr(self, "_tei_embedding_active", 0),
            "tei_reranker_active": getattr(self, "_tei_reranker_active", 0),
            "tei_pool_timeout_total": getattr(self, "_tei_pool_timeout_total", 0),
        }

    async def embed_documents(
        self, documents: List[str]
    ) -> list[list[float]]:
        """Embed raw stored documents without a role prompt."""
        self._ensure_open()
        try:
            return await self.embedding_client.embed_documents(documents)
        except httpx.TimeoutException as exc:
            raise ServiceTimeoutError("Embedding service timed out") from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(
                "Embedding service is unavailable"
            ) from exc

    def embed_documents_sync(self, documents: List[str]) -> list[list[float]]:
        """Embed raw documents from FastAPI's synchronous KB worker paths."""
        self._ensure_open()
        request_payload = build_document_payload(documents)
        if not documents:
            return []
        try:
            resp = self._sync_http.post(
                f"{self.tei_embed_url}/embed",
                json=request_payload,
            )
            resp.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ServiceTimeoutError("Embedding service timed out") from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(
                "Embedding service is unavailable"
            ) from exc
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ServiceProtocolError(
                "Embedding service returned an invalid response"
            ) from exc
        return validate_embedding_response(
            payload,
            expected_count=len(documents),
            expected_dimension=self._expected_embedding_dimensions,
        )

    def _ensure_open(self) -> None:
        if getattr(self, "_closed", False):
            raise RuntimeError("search client is closed")

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_http:
            await self._http.aclose()
        if self._owns_sync_http:
            await self._blocking_runner.run(self._sync_http.close)
        if self._owns_blocking_runner:
            await self._blocking_runner.aclose()


    def set_chunk_fetcher(self, fetcher: Callable[[List[str]], Dict[str, dict]]):
        """Provide a function that retrieves chunk texts from the database."""
        self.chunk_fetcher = fetcher

    def clear_document_cache(self) -> int:
        """Discard process-local BM25 corpora after ingestion or reset."""
        return self._bm25_cache.clear()

    # ------------------------------------------------------------------
    #  Fetch chunks for the given document names
    # ------------------------------------------------------------------
    def _fetch_chunks(self, document_names: List[str]) -> Dict[str, dict]:
        """
        Returns dict of chunk_id -> { 'text': str, 'document_name': str, ... }
        Raises error if chunk_fetcher not set.
        """
        if not self.chunk_fetcher:
            raise RuntimeError(
                "No chunk_fetcher provided. Please call set_chunk_fetcher() with a database callback."
            )
        return self.chunk_fetcher(document_names)

    # ------------------------------------------------------------------
    #  BM25 – built dynamically
    # ------------------------------------------------------------------
    def _build_temporary_bm25(self, chunk_dict: Dict[str, dict]) -> Tuple[BM25Okapi, List[str], np.ndarray]:
        """
        Given a dict of chunk_id -> metadata (must contain 'text'),
        tokenise all texts and return (BM25Okapi, list_of_chunk_ids, corpus_texts).
        """
        corpus_texts = []
        chunk_ids = []
        tokenised = []
        for cid, info in chunk_dict.items():
            corpus_texts.append(info["text"])
            chunk_ids.append(cid)
            tokenised.append(self.processor.process(
                info["text"],
                apply_document_overrides=True,
            ))
        bm25 = BM25Okapi(tokenised)
        return bm25, chunk_ids, corpus_texts

    # ------------------------------------------------------------------
    #  Semantic search with Qdrant + document filter
    # ------------------------------------------------------------------
    async def _semantic_search(self, query: str, document_names: list, top_k: int) -> dict:
        query_vec = await self._encode_query(query)
        doc_filter = qdrant_models.Filter(
            must=[qdrant_models.FieldCondition(
                key="document", match=qdrant_models.MatchAny(any=document_names)
            )]
        )
        # qdrant-client's sync query_points is a blocking network call — push to a thread
        trace = current_trace()
        if trace is not None:
            trace.mark("qdrant_wait_start")
        qdrant_wait_started = time.perf_counter_ns()
        self._qdrant_waiting += 1
        try:
            await self._qdrant_semaphore.acquire()
        finally:
            self._qdrant_waiting -= 1
        self._qdrant_active += 1
        self._qdrant_acquired_total += 1
        if trace is not None:
            trace.mark("qdrant_acquired")
            trace.add_duration(
                "qdrant_wait",
                (time.perf_counter_ns() - qdrant_wait_started) / 1_000_000,
            )
        try:
            try:
                async with trace_span("qdrant"):
                    results = await self._blocking_runner.run(
                        self.qdrant_client.query_points,
                        collection_name=self.collection_name,
                        query=query_vec,
                        limit=top_k,
                        query_filter=doc_filter,
                        with_payload=["chunk_id"],
                        with_vectors=False,
                    )
            except asyncio.CancelledError:
                raise
            except TimeoutError as exc:
                raise ServiceTimeoutError(
                    "Vector search service timed out"
                ) from exc
            except Exception as exc:
                raise ServiceUnavailableError(
                    "Vector search service is unavailable"
                ) from exc
        finally:
            self._qdrant_active -= 1
            self._qdrant_released_total += 1
            self._qdrant_semaphore.release()
            if trace is not None:
                trace.mark("qdrant_end")
        semantic_results = sorted(
            (
                hit
                for hit in results.points
                if "chunk_id" in hit.payload
            ),
            key=lambda hit: (
                -hit.score,
                str(hit.payload["chunk_id"]),
            ),
        )
        return {
            str(hit.payload["chunk_id"]): hit.score
            for hit in semantic_results
        }



    def _get_or_build_bm25(self, allowed_docs: list):
        key = tuple(sorted(allowed_docs))
        revision = (
            self.chunk_revision_fetcher(list(key))
            if self.chunk_revision_fetcher
            else None
        )

        def build():
            chunk_dict = self._fetch_chunks(allowed_docs)
            with self._processor_lock:
                bm25, chunk_ids, _ = self._build_temporary_bm25(chunk_dict)
            return bm25, chunk_ids, chunk_dict

        return self._bm25_cache.get_or_build(key, revision, build)

    def _process_query(self, query: str) -> list[str]:
        with self._processor_lock:
            return self.processor.process(
                query,
                apply_document_overrides=False,
            )

    def _normalise_query(self, query: str) -> str:
        with self._processor_lock:
            return normalize_persian_text(self.processor.normalize(query))

    # ------------------------------------------------------------------
    #  Score normalisation
    # ------------------------------------------------------------------
    @staticmethod
    def _normalise(arr: np.ndarray) -> np.ndarray:
        if arr.size == 0:
            return arr
        mn, mx = arr.min(), arr.max()
        return (arr - mn) / (mx - mn + 1e-10)

    # ------------------------------------------------------------------
    #  Main search
    # ------------------------------------------------------------------
    async def search(self, query: str, top_k: int | None = None, rerank: bool = False,
                      allowed_docs: list = None) -> list:
        search_started = time.perf_counter()
        if not allowed_docs:
            raise ValueError("allowed_docs must be provided for filtered search.")
        top_k = top_k or PERFORMANCE_SETTINGS.rag_retrieval_top_k

        # CPU-bound Persian NLP + BM25 lookup — off the event loop
        bm25, bm25_chunk_ids, chunk_dict = await self._blocking_runner.run(
            self._get_or_build_bm25, allowed_docs
        )
        if not chunk_dict:
            emit_pipeline_stage_lazy(lambda: PipelineStageResult(
                stage=PipelineStage.RETRIEVAL,
                input_data={
                    "retrieval_query": query,
                    "allowed_docs": list(allowed_docs),
                    "top_k": top_k,
                },
                output_data={"candidates": []},
                metrics={
                    "semantic_candidate_limit": PERFORMANCE_SETTINGS.rag_semantic_candidate_limit,
                    "reason": "NO_CHUNKS",
                },
                duration_ms=(time.perf_counter() - search_started) * 1000,
            ))
            return []
        query_tokens = await self._blocking_runner.run(
            self._process_query, query
        )
        bm25_scores, bm25_candidates = await self._blocking_runner.run(
            self._score_bm25, bm25, bm25_chunk_ids, query_tokens
        )
        bm25_top_ids = [cid for cid, score in bm25_candidates if score > 0]

        semantic_query = await self._blocking_runner.run(
            self._normalise_query, query
        )
        semantic_scores_map = await self._semantic_search(
            semantic_query,
            allowed_docs,
            top_k=PERFORMANCE_SETTINGS.rag_semantic_candidate_limit,
        )
        semantic_top_ids = list(semantic_scores_map.keys())

        candidate_ids = list(dict.fromkeys(
            bm25_top_ids + semantic_top_ids
        ))
        if not candidate_ids:
            emit_pipeline_stage_lazy(lambda: PipelineStageResult(
                stage=PipelineStage.RETRIEVAL,
                input_data={
                    "retrieval_query": query,
                    "semantic_query": semantic_query,
                    "allowed_docs": list(allowed_docs),
                    "top_k": top_k,
                },
                output_data={"candidates": []},
                metrics={
                    "semantic_candidate_limit": PERFORMANCE_SETTINGS.rag_semantic_candidate_limit,
                    "reason": "NO_CANDIDATES",
                },
                duration_ms=(time.perf_counter() - search_started) * 1000,
            ))
            return []

        RRF_K = 60
        bm25_rank = {
            cid: rank for rank, cid in enumerate(bm25_top_ids, start=1)
        }
        semantic_rank = {
            cid: rank for rank, cid in enumerate(semantic_top_ids, start=1)
        }
        bm25_scores_map = dict(bm25_candidates)
        hybrid_scores = {}
        for cid in candidate_ids:
            rank_b = bm25_rank.get(cid, 61)
            rank_s = semantic_rank.get(cid, 61)
            hybrid_scores[cid] = {
                "hybrid": (1.0 / (RRF_K + rank_b)) + (1.0 / (RRF_K + rank_s)),
                "bm25": bm25_scores_map.get(cid, 0.0),
                "semantic": semantic_scores_map.get(cid, 0.0),
            }

        sorted_ids = sorted(
            hybrid_scores,
            key=lambda cid: (
                -hybrid_scores[cid]["hybrid"],
                -hybrid_scores[cid]["semantic"],
                -hybrid_scores[cid]["bm25"],
                str(cid),
            ),
        )[:top_k]
        search_results = [
            SearchResult(
                doc_id=cid, content=chunk_dict[cid]["text"],
                score=round(hybrid_scores[cid]["hybrid"], 6),
                bm25_score=round(hybrid_scores[cid]["bm25"], 6),
                semantic_score=round(hybrid_scores[cid]["semantic"], 6),
                metadata={"document_name": chunk_dict[cid].get("document_name", "")},
                original_rrf_rank=original_rrf_rank,
            )
            for original_rrf_rank, cid in enumerate(sorted_ids, start=1)
        ]
        trace = current_trace()
        if trace is not None:
            trace.set_diagnostic(
                "retrieval_top",
                [
                    {
                        "candidate_id": result.doc_id,
                        "hybrid_score": result.score,
                        "semantic_score": result.semantic_score,
                        "bm25_score": result.bm25_score,
                    }
                    for result in search_results[:10]
                ],
            )
        emit_pipeline_stage_lazy(lambda: PipelineStageResult(
            stage=PipelineStage.RETRIEVAL,
            input_data={
                "retrieval_query": query,
                "semantic_query": semantic_query,
                "allowed_docs": list(allowed_docs),
                "top_k": top_k,
            },
            output_data={
                "candidates": [
                    {
                        "chunk_id": result.doc_id,
                        "rank": rank,
                        "original_rrf_rank": result.original_rrf_rank,
                        "retrieval_score": result.score,
                        "bm25_score": result.bm25_score,
                        "semantic_score": result.semantic_score,
                        "content": result.content,
                        "metadata": result.metadata or {},
                    }
                    for rank, result in enumerate(search_results, start=1)
                ]
            },
            metrics={
                "semantic_candidate_limit": PERFORMANCE_SETTINGS.rag_semantic_candidate_limit,
                "rrf_k": RRF_K,
                "embedding_dimension": 1024,
                "embedding_prompt_name": "query",
            },
            duration_ms=(time.perf_counter() - search_started) * 1000,
        ))
        return search_results

    @staticmethod
    def _score_bm25(bm25, chunk_ids, query_tokens):
        scores = bm25.get_scores(query_tokens)
        candidates = sorted(
            zip(chunk_ids, scores),
            key=lambda item: (-item[1], str(item[0])),
        )[:50]
        return scores, candidates


    async def rerank_search_results(
        self,
        query: str,
        candidates: list[SearchResult],
        top_k: int,
    ) -> list[SearchResult]:
        """Rerank full answer chunks once while preserving first-stage scores."""

        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        rerank_started = time.perf_counter()
        normalized_query = normalize_persian_text(query)
        texts = [
            normalize_persian_text(candidate.content)
            for candidate in candidates
        ]
        candidate_rows = [
            {
                "chunk_id": str(candidate.doc_id),
                "original_rrf_rank": (
                    candidate.original_rrf_rank or input_rank
                ),
                "hybrid_score": candidate.score,
                "bm25_score": candidate.bm25_score,
                "semantic_score": candidate.semantic_score,
            }
            for input_rank, candidate in enumerate(candidates, start=1)
        ]

        if not candidates:
            emit_pipeline_stage_lazy(lambda: PipelineStageResult(
                stage=PipelineStage.RERANK,
                input_data={"candidates": []},
                output_data={"rankings": []},
                metrics={
                    "purpose": "answer_context",
                    "candidate_count": 0,
                    "selected_count": 0,
                    "top_k": top_k,
                    "raw_scores": False,
                },
                duration_ms=(time.perf_counter() - rerank_started) * 1000,
            ))
            return []

        self._ensure_open()
        self._tei_reranker_active = getattr(
            self, "_tei_reranker_active", 0
        ) + 1
        try:
            try:
                async with trace_span("reranker"):
                    response = await self._http.post(
                        f"{self.tei_rerank_url}/rerank",
                        json={
                            "query": normalized_query,
                            "texts": texts,
                            "raw_scores": False,
                        },
                    )
                    response.raise_for_status()
            except httpx.PoolTimeout as exc:
                self._tei_pool_timeout_total = getattr(
                    self, "_tei_pool_timeout_total", 0
                ) + 1
                raise ServiceTimeoutError(
                    "Reranking HTTP pool timed out"
                ) from exc
            except httpx.TimeoutException as exc:
                raise ServiceTimeoutError(
                    "Reranking service timed out"
                ) from exc
            except httpx.HTTPError as exc:
                raise ServiceUnavailableError(
                    "Reranking service is unavailable"
                ) from exc

            try:
                rankings = response.json()
            except ValueError as exc:
                raise ServiceProtocolError(
                    "Reranking service returned an invalid response"
                ) from exc
            if not isinstance(rankings, list) or len(rankings) != len(candidates):
                raise ServiceProtocolError(
                    "Reranking service returned an incomplete response"
                )

            seen_indexes = set()
            scored_candidates = []
            for ranking in rankings:
                if not isinstance(ranking, dict):
                    raise ServiceProtocolError(
                        "Reranking service returned an invalid response"
                    )
                index = ranking.get("index")
                score = ranking.get("score")
                if (
                    isinstance(index, bool)
                    or not isinstance(index, int)
                    or index < 0
                    or index >= len(candidates)
                    or index in seen_indexes
                ):
                    raise ServiceProtocolError(
                        "Reranking service returned an invalid response"
                    )
                if (
                    isinstance(score, bool)
                    or not isinstance(score, (int, float))
                    or not math.isfinite(score)
                ):
                    raise ServiceProtocolError(
                        "Reranking service returned an invalid response"
                    )
                seen_indexes.add(index)
                candidate = candidates[index]
                scored_candidates.append((
                    candidate,
                    float(score),
                    candidate.original_rrf_rank or index + 1,
                ))
        except Exception as exc:
            emit_pipeline_stage_lazy(lambda: PipelineStageResult(
                stage=PipelineStage.RERANK,
                status="ERROR",
                input_data={"candidates": candidate_rows},
                metrics={
                    "purpose": "answer_context",
                    "candidate_count": len(candidates),
                    "top_k": top_k,
                    "raw_scores": False,
                },
                duration_ms=(time.perf_counter() - rerank_started) * 1000,
                error_code=getattr(exc, "error_code", type(exc).__name__),
                error_data={"error_type": type(exc).__name__},
            ))
            raise
        finally:
            self._tei_reranker_active -= 1

        scored_candidates.sort(key=lambda item: (
            -item[1],
            item[2],
            str(item[0].doc_id),
        ))
        ranked_candidates = [
            replace(
                candidate,
                original_rrf_rank=original_rrf_rank,
                reranker_score=score,
                reranker_rank=reranker_rank,
            )
            for reranker_rank, (
                candidate,
                score,
                original_rrf_rank,
            ) in enumerate(scored_candidates, start=1)
        ]
        selected_count = min(top_k, len(ranked_candidates))
        ranking_rows = [
            {
                "chunk_id": str(candidate.doc_id),
                "original_rrf_rank": candidate.original_rrf_rank,
                "hybrid_score": candidate.score,
                "bm25_score": candidate.bm25_score,
                "semantic_score": candidate.semantic_score,
                "reranker_score": candidate.reranker_score,
                "reranker_rank": candidate.reranker_rank,
                "selected": bool(candidate.reranker_rank <= selected_count),
            }
            for candidate in ranked_candidates
        ]
        trace = current_trace()
        if trace is not None:
            trace.set_diagnostic(
                "context_rerank_top", ranking_rows[:selected_count]
            )
        emit_pipeline_stage_lazy(lambda: PipelineStageResult(
            stage=PipelineStage.RERANK,
            input_data={"candidates": candidate_rows},
            output_data={"rankings": ranking_rows},
            metrics={
                "purpose": "answer_context",
                "candidate_count": len(candidates),
                "selected_count": selected_count,
                "top_k": top_k,
                "raw_scores": False,
            },
            duration_ms=(time.perf_counter() - rerank_started) * 1000,
        ))
        return ranked_candidates[:selected_count]

    async def rerank(
        self,
        query: str,
        candidates: list[dict],
        threshold: float,
    ) -> list[dict]:
        rerank_started = time.perf_counter()
        normalized_query = normalize_persian_text(query)
        texts = [
            normalize_persian_text(candidate.get("question", ""))
            for candidate in candidates
        ]
        self._ensure_open()
        self._tei_reranker_active = getattr(
            self, "_tei_reranker_active", 0
        ) + 1
        try:
            async with trace_span("reranker"):
                resp = await self._http.post(
                    f"{self.tei_rerank_url}/rerank",
                    json={"query": normalized_query, "texts": texts},
                )
                resp.raise_for_status()
        except httpx.PoolTimeout as exc:
            self._tei_pool_timeout_total = getattr(
                self, "_tei_pool_timeout_total", 0
            ) + 1
            raise ServiceTimeoutError("Reranking HTTP pool timed out") from exc
        except httpx.TimeoutException as exc:
            raise ServiceTimeoutError("Reranking service timed out") from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(
                "Reranking service is unavailable"
            ) from exc
        finally:
            self._tei_reranker_active -= 1
        try:
            rankings = resp.json()
        except ValueError as exc:
            raise ServiceProtocolError(
                "Reranking service returned an invalid response"
            ) from exc
        if not isinstance(rankings, list):
            raise ServiceProtocolError(
                "Reranking service returned an invalid response"
            )

        ranked_candidates = []
        trace_rankings = []
        seen_indexes = set()
        output_rows = []
        for output_rank, ranking in enumerate(rankings, start=1):
            if not isinstance(ranking, dict):
                raise ServiceProtocolError(
                    "Reranking service returned an invalid response"
                )
            index = ranking.get("index")
            score = ranking.get("score")
            if not isinstance(index, int) or index < 0 or index >= len(candidates):
                raise ServiceProtocolError(
                    "Reranking service returned an invalid response"
                )
            if index in seen_indexes:
                raise ServiceProtocolError(
                    "Reranking service returned an invalid response"
                )
            if (
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not math.isfinite(score)
            ):
                raise ServiceProtocolError(
                    "Reranking service returned an invalid response"
                )
            seen_indexes.add(index)
            trace_rankings.append(
                {
                    "candidate_id": str(
                        candidates[index].get("_trace_id", index)
                    ),
                    "score": round(float(score), 8),
                    "accepted": bool(score >= threshold),
                }
            )
            output_rows.append({
                "candidate_id": str(candidates[index].get("_trace_id", index)),
                "input_rank": index + 1,
                "output_rank": output_rank,
                "score": float(score),
                "accepted": bool(score >= threshold),
                "candidate": candidates[index],
            })
            if score >= threshold:
                ranked_candidates.append(candidates[index])

        trace = current_trace()
        if trace is not None:
            trace.set_diagnostic(
                "related_questions_rerank_top", trace_rankings[:10]
            )
            trace.set_diagnostic(
                "related_questions_rerank_threshold", threshold
            )

        emit_pipeline_stage_lazy(lambda: PipelineStageResult(
            stage=PipelineStage.RERANK,
            input_data={
                "auxiliary_related_questions": {
                    "query": query,
                    "normalized_query": normalized_query,
                    "candidates": [
                        {"input_rank": rank, "candidate": candidate}
                        for rank, candidate in enumerate(candidates, start=1)
                    ],
                },
            },
            output_data={
                "auxiliary_related_questions": {"rankings": output_rows}
            },
            metrics={
                "auxiliary_related_questions": {
                    "purpose": "related_questions",
                    "threshold": threshold,
                }
            },
            duration_ms=(time.perf_counter() - rerank_started) * 1000,
        ))

        return ranked_candidates[:5]
