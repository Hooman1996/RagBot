import numpy as np
import asyncio
import math
import threading
from typing import List, Dict, Tuple, Optional, Callable
from dataclasses import dataclass
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
from utils.tei_embedding_client import (
    TeiEmbeddingClient,
    build_document_payload,
    validate_embedding_response,
)

@dataclass
class SearchResult:
    """Search result container"""
    doc_id: str
    content: str
    score: float
    bm25_score: float
    semantic_score: float
    metadata: Optional[Dict] = None


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
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def tokenize(self, text: str) -> List[str]:
        try:
            return self.tokenizer.tokenize_words(text)
        except Exception:
            return text.split()

    def stem(self, tokens: List[str]) -> List[str]:
        if not self.use_stemming:
            return tokens

        stemmed = []

        # 1. Stop-Stem Dictionary: Words that end in م, ت, ش, ی but are root words
        do_not_strip = {
            'انگشت', 'کارت', 'ثبت', 'دست', 'پاسپورت', 'بلیت',
            'ساعت', 'قیمت', 'شرکت', 'شکایت', 'امنیت', 'هویت',
            'سایت', 'اکانت', 'فرمت', 'چت', 'ربات', 'کد', 'اینترنت'
        }

        # 2. Slang overrides applied BEFORE any stemming
        slang_overrides = {
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
            # Check slang dictionary first
            if token in slang_overrides:
                stemmed.append(slang_overrides[token])
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

    def process(self, text: str, remove_stopwords: bool = True, apply_stemming: bool = True) -> List[str]:
        text = self.normalize(text)
        tokens = self.tokenize(text)
        if remove_stopwords:
            tokens = self.remove_stopwords(tokens)
        if apply_stemming and self.use_stemming:
            tokens = self.stem(tokens)
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
        self._bm25_cache: dict[tuple, tuple] = {}
        self._processor_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._blocking_runner = blocking_runner or BoundedBlockingRunner()
        self._owns_blocking_runner = blocking_runner is None
        self._qdrant_semaphore = asyncio.Semaphore(
            qdrant_concurrency or PERFORMANCE_SETTINGS.qdrant_concurrency
        )
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


    async def _encode_query(self, query: str) -> list[float]:
        self._ensure_open()
        try:
            return await self.embedding_client.embed_query(query)
        except httpx.TimeoutException as exc:
            raise ServiceTimeoutError("Embedding service timed out") from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(
                "Embedding service is unavailable"
            ) from exc

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

    def _expand_query_intent(self, query: str) -> str:
        """
        Rewrites/Expands short colloquial phrases to align with documentation terminology.
        """
        query_clean = query.strip()

        # Rule-based intent expansion mapping
        intent_map = {
            r"\bانگشتم\b": "اثر انگشت من سنسور زیستی",
            # r"ثبت\s+نمی[‌ ]*شه": "عدم ثبت خطای فعال سازی",
            r"\bرمزم\b": "رمز من",
            r"\bاس ام اس\b": "پیامک",
            # r"\bقسطم\b": "پرداخت اقسط وام",
            # r"\bوامم\b": "تسهیلات وام"
        }

        for pattern, expansion in intent_map.items():
            query_clean = re.sub(pattern, expansion, query_clean)

        return query_clean

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
            tokenised.append(self.processor.process(info["text"]))
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
        async with self._qdrant_semaphore:
            try:
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
        return {str(hit.payload["chunk_id"]): hit.score
                for hit in results.points if "chunk_id" in hit.payload}



    def _get_or_build_bm25(self, allowed_docs: list):
        key = tuple(sorted(allowed_docs))
        with self._cache_lock:
            if key not in self._bm25_cache:
                chunk_dict = self._fetch_chunks(allowed_docs)
                with self._processor_lock:
                    bm25, chunk_ids, _ = self._build_temporary_bm25(chunk_dict)
                self._bm25_cache[key] = (bm25, chunk_ids, chunk_dict)
            return self._bm25_cache[key]

    def _process_query(self, query: str) -> list[str]:
        with self._processor_lock:
            return self.processor.process(query)

    def _normalise_query(self, query: str) -> str:
        with self._processor_lock:
            return self.processor.normalize(query).replace("\u200c", " ")

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
        if not allowed_docs:
            raise ValueError("allowed_docs must be provided for filtered search.")
        top_k = top_k or PERFORMANCE_SETTINGS.rag_retrieval_top_k

        expanded_query = self._expand_query_intent(query)

        # CPU-bound Persian NLP + BM25 lookup — off the event loop
        bm25, bm25_chunk_ids, chunk_dict = await self._blocking_runner.run(
            self._get_or_build_bm25, allowed_docs
        )
        if not chunk_dict:
            return []
        query_tokens = await self._blocking_runner.run(
            self._process_query, expanded_query
        )
        bm25_scores, bm25_candidates = await self._blocking_runner.run(
            self._score_bm25, bm25, bm25_chunk_ids, query_tokens
        )
        bm25_top_ids = [cid for cid, score in bm25_candidates if score > 0]

        semantic_query = await self._blocking_runner.run(
            self._normalise_query, expanded_query
        )
        semantic_scores_map = await self._semantic_search(
            semantic_query,
            allowed_docs,
            top_k=PERFORMANCE_SETTINGS.rag_semantic_candidate_limit,
        )
        semantic_top_ids = list(semantic_scores_map.keys())

        candidate_ids = list(set(bm25_top_ids + semantic_top_ids))
        if not candidate_ids:
            return []

        RRF_K = 60
        hybrid_scores = {}
        for cid in candidate_ids:
            rank_b = bm25_top_ids.index(cid) + 1 if cid in bm25_top_ids else 61
            rank_s = semantic_top_ids.index(cid) + 1 if cid in semantic_top_ids else 61
            hybrid_scores[cid] = {
                "hybrid": (1.0 / (RRF_K + rank_b)) + (1.0 / (RRF_K + rank_s)),
                "bm25": next((s for c, s in bm25_candidates if c == cid), 0.0),
                "semantic": semantic_scores_map.get(cid, 0.0),
            }

        sorted_ids = sorted(hybrid_scores.keys(), key=lambda c: hybrid_scores[c]["hybrid"], reverse=True)[:top_k]
        return [
            SearchResult(
                doc_id=cid, content=chunk_dict[cid]["text"],
                score=round(hybrid_scores[cid]["hybrid"], 6),
                bm25_score=round(hybrid_scores[cid]["bm25"], 6),
                semantic_score=round(hybrid_scores[cid]["semantic"], 6),
                metadata={"document_name": chunk_dict[cid].get("document_name", "")},
            )
            for cid in sorted_ids
        ]

    @staticmethod
    def _score_bm25(bm25, chunk_ids, query_tokens):
        scores = bm25.get_scores(query_tokens)
        candidates = sorted(
            zip(chunk_ids, scores), key=lambda item: item[1], reverse=True
        )[:50]
        return scores, candidates


    async def rerank(
        self,
        query: str,
        candidates: list[dict],
        threshold: float,
    ) -> list[dict]:
        texts = [candidate.get("question", "") for candidate in candidates]
        self._ensure_open()
        try:
            resp = await self._http.post(
                f"{self.tei_rerank_url}/rerank",
                json={"query": query, "texts": texts},
            )
            resp.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ServiceTimeoutError("Reranking service timed out") from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(
                "Reranking service is unavailable"
            ) from exc
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
        seen_indexes = set()
        for ranking in rankings:
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
            if score >= threshold:
                ranked_candidates.append(candidates[index])

        return ranked_candidates[:5]
