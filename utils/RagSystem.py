from qdrant_client import QdrantClient

from .persian_hybrid_search import PersianHybridSearch
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import json
from pathlib import Path
import re
import torch
import os
import time
from langchain_classic.chains import RetrievalQA

from dotenv import load_dotenv
load_dotenv()

# 1. Replace Hugging Face & Torch imports with the OpenAI client
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
import httpx
from utils.concurrency import BoundedBlockingRunner
from utils.performance_config import PERFORMANCE_SETTINGS
from utils.service_errors import (
    ModelContextLengthError,
    ServiceProtocolError,
    ServiceTimeoutError,
    ServiceUnavailableError,
)
from utils.request_instrumentation import current_trace, trace_span
from new_architecture.app.config import Config
from .rag_utils import clean_llm_answer
from pipeline_observer import (
    PipelineStage,
    PipelineStageResult,
    emit_pipeline_stage_lazy,
    pipeline_hashes_enabled,
    stable_hash,
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


class RAGSystem:
    """
    Complete RAG system with hybrid search and document chunking
    """

    def __init__(
            self,
            reranker_model_id: str = os.getenv("RERANKER_MODEL"),
            use_gpu: bool = True,
            model_id: str = "/app/model",
            qdrant_client: Optional[QdrantClient] = None,
            chunk_fetcher = None,
            chunk_revision_fetcher = None,
            vllm_url: str = os.getenv("VLLM_URL", "http://localhost:8000/v1"),
            tei_rerank_url: str = os.getenv("TEI_RERANK_URL", "http://localhost:7998"),
            llm_client: Optional[AsyncOpenAI] = None,
            tei_http_client: Optional[httpx.AsyncClient] = None,
            tei_sync_http_client: Optional[httpx.Client] = None,
            blocking_runner: Optional[BoundedBlockingRunner] = None,

    ):
        """
        Initialize RAG system

        Args:
            embedding_model: Embedding model name
            use_gpu: Whether to use GPU
            search_results: Search results to use
        """



        self.model_id = model_id

        # self.processor = AutoProcessor.from_pretrained(model_id)

        self._owns_client = llm_client is None
        self.client = llm_client or AsyncOpenAI(
            base_url=vllm_url,
            api_key="vllm-token-not-needed",
            timeout=httpx.Timeout(
                connect=(
                    PERFORMANCE_SETTINGS.vllm_http_connect_timeout_seconds
                ),
                read=PERFORMANCE_SETTINGS.vllm_http_read_timeout_seconds,
                write=PERFORMANCE_SETTINGS.vllm_http_write_timeout_seconds,
                pool=PERFORMANCE_SETTINGS.vllm_http_pool_timeout_seconds,
            ),
            max_retries=0,
            http_client=httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=(
                        PERFORMANCE_SETTINGS.vllm_http_connect_timeout_seconds
                    ),
                    read=PERFORMANCE_SETTINGS.vllm_http_read_timeout_seconds,
                    write=PERFORMANCE_SETTINGS.vllm_http_write_timeout_seconds,
                    pool=PERFORMANCE_SETTINGS.vllm_http_pool_timeout_seconds,
                ),
                limits=httpx.Limits(
                    max_connections=(
                        PERFORMANCE_SETTINGS.vllm_http_max_connections
                    ),
                    max_keepalive_connections=(
                        PERFORMANCE_SETTINGS.vllm_http_max_keepalive_connections
                    ),
                    keepalive_expiry=(
                        PERFORMANCE_SETTINGS.vllm_http_keepalive_expiry_seconds
                    ),
                ),
            ),
        )
        self.tei_rerank_url = tei_rerank_url
        self._closed = False
        self.blocking_runner = blocking_runner or BoundedBlockingRunner()
        self._owns_blocking_runner = blocking_runner is None
        self._vllm_active = 0
        self._vllm_timeout_total = 0

        self.qdrant_client = qdrant_client
        self.chunk_fetcher = chunk_fetcher
        self.chunk_revision_fetcher = chunk_revision_fetcher
        # pipe = pipeline("text-generation", model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B", device_map= 'auto')
        # self.tokenizer = tokenizer
        # self.model = pipe

        print("Initializing RAG System...")

        self.search_engine = PersianHybridSearch(
            # use_embeddings=True,
            # cache_dir="/home/hooman/Downloads/cached_models",
            use_gpu=True,
            qdrant_client = self.qdrant_client,
            chunk_fetcher= self.chunk_fetcher,
            chunk_revision_fetcher=self.chunk_revision_fetcher,
            http_client=tei_http_client,
            sync_http_client=tei_sync_http_client,
            blocking_runner=self.blocking_runner,
        )

        # self.rerank_tokenizer = AutoTokenizer.from_pretrained(reranker_model_id)
        #
        # self.reranker_model = AutoModelForSequenceClassification.from_pretrained(
        #     reranker_model_id, trust_remote_code=True,
        #     torch_dtype=torch.float16
        # )

        # Create a prompt template

        print("RAG System initialized!")

    def get_model_and_processor(self):
        # Kept for backward compatibility if other scripts call it,
        # though vLLM handles processing under the hood now.
        return self.client, None

    def add_documents(
            self, documents: List[str]):
        """
        Add documents to RAG system

        Args:
            documents: List of documents
        """
        self.search_engine.add_documents(documents=documents)

    async def retrieve(self, query, top_k=None, allowed_docs=None, rerank=False):
        self._ensure_open()
        results = await self.search_engine.search(
            query=query,
            top_k=top_k or PERFORMANCE_SETTINGS.rag_retrieval_top_k,
            allowed_docs=allowed_docs,
        )
        return results

    def _ensure_open(self):
        if self._closed:
            raise RuntimeError("RAG service is closed")

    async def aclose(self):
        if self._closed:
            return
        self._closed = True
        await self.search_engine.aclose()
        if self._owns_blocking_runner:
            await self.blocking_runner.aclose()
        if self._owns_client:
            await self.client.close()

    async def _completion(self, **kwargs):
        self._ensure_open()
        trace = current_trace()
        if trace is not None:
            trace.set_diagnostic(
                "generation_temperature", kwargs.get("temperature")
            )
            trace.set_diagnostic("generation_top_p", kwargs.get("top_p"))
            trace.set_diagnostic("generation_seed", kwargs.get("seed"))
        self._vllm_active += 1
        try:
            async with trace_span("vllm"):
                return await self.client.chat.completions.create(**kwargs)
        except APITimeoutError as exc:
            self._vllm_timeout_total += 1
            raise ServiceTimeoutError("Language model service timed out") from exc
        except APIStatusError as exc:
            body = exc.body if isinstance(exc.body, dict) else {}
            if exc.status_code == 400 and body.get("param") == "input_tokens":
                raise ModelContextLengthError(
                    "Language model context limit exceeded"
                ) from exc
            if 400 <= exc.status_code < 500:
                raise ServiceProtocolError(
                    "Language model rejected the request"
                ) from exc
            raise ServiceUnavailableError(
                "Language model service is unavailable"
            ) from exc
        except APIConnectionError as exc:
            raise ServiceUnavailableError(
                "Language model service is unavailable"
            ) from exc
        finally:
            self._vllm_active -= 1

    def metrics_snapshot(self) -> dict[str, int]:
        return {
            "vllm_active": self._vllm_active,
            "vllm_timeout_total": self._vllm_timeout_total,
        }

    def generate_context(self, results: List[SearchResult]) -> str:
        """
        Generate context string from search results

        Args:
            results: List of search results

        Returns:
            Formatted context string
        """

        """
            Converts search results into deeply nested XML for precise LLM parsing.
            """
        ordered_results = list(results)
        formatted_documents = []

        for index, result in enumerate(ordered_results, start=1):
            raw_content = result.content

            # 1. Extract Question
            question_match = re.search(r'question\s*:\s*(.*?)(?=\nanswer\s*:)', raw_content, re.DOTALL)
            question_text = question_match.group(1).strip() if question_match else ""

            # 2. Extract Answer
            answer_match = re.search(r'answer\s*:\s*(.*?)(?=\nquestion category\s*:|$)', raw_content, re.DOTALL)
            answer_text = answer_match.group(1).strip() if answer_match else ""

            # 3. Extract Categories
            category_match = re.search(r'question category\s*:\s*(.*)', raw_content, re.DOTALL)
            main_cat, sub_cat = "", ""

            if category_match:
                cat_string = category_match.group(1).strip()
                # Split main and sub category based on your dataset's pattern (". sub_category :")
                cat_parts = re.split(r'\.?\s*sub_category\s*:\s*', cat_string)
                main_cat = cat_parts[0].strip(' .»')
                if len(cat_parts) > 1:
                    sub_cat = cat_parts[1].strip(' .»')

            # 4. Construct the XML Node
            doc_xml = f"""<doc id="{index}">
          <question>{question_text}</question>
          <answer>{answer_text}</answer>
          <main_category>{main_cat}</main_category>"""

            # Only add sub_category tag if it exists
            if sub_cat:
                doc_xml += f"\n  <sub_category>{sub_cat}</sub_category>"

            doc_xml += "\n</doc>"

            formatted_documents.append(doc_xml)

        return "\n".join(formatted_documents)

        return context

    async def answer(self, user_question, context, recent_history, current_summary, tone, response_type,
               max_new_tokens=None,
               enable_history=True, category=None):

        prompt_started = time.perf_counter()
        max_new_tokens = (
            max_new_tokens or PERFORMANCE_SETTINGS.rag_max_new_tokens
        )
        if category == "chitchat":
            max_new_tokens = PERFORMANCE_SETTINGS.rag_chitchat_max_new_tokens
            generation_temperature = (
                PERFORMANCE_SETTINGS.rag_chitchat_temperature
            )
            generation_top_p = PERFORMANCE_SETTINGS.rag_chitchat_top_p
            generation_seed = PERFORMANCE_SETTINGS.rag_chitchat_seed
        else:
            generation_temperature = PERFORMANCE_SETTINGS.rag_answer_temperature
            generation_top_p = PERFORMANCE_SETTINGS.rag_answer_top_p
            generation_seed = PERFORMANCE_SETTINGS.rag_answer_seed

        if category == "chitchat":
            system_prompt_template = Config.CHITCHAT_SYSTEM_PROMPT
            user_prompt_template = Config.CHITCHAT_USER_PROMPT
            user_prompt = user_prompt_template.format(
                current_history=recent_history,
                question=user_question
            )

        elif category == "ابلاغیه ها" or category == "قرارداد ها":
            system_prompt_template = Config.DOCUMENT_RAG_SYSTEM_PROMPT
            user_prompt_template = Config.DOCUMENT_RAG_USER_PROMPT
            user_prompt = user_prompt_template.format(
                current_context=context,
                current_history=recent_history,
                current_question=user_question
            )

        else:
            system_prompt_template = Config.GENERAL_RAG_SYSTEM_PROMPT
            user_prompt_template = Config.GENERAL_RAG_USER_PROMPT
            user_prompt = user_prompt_template.format(
                formatted_search_results=context,
                question=user_question
            )

        system_message = system_prompt_template
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt},
        ]
        emit_pipeline_stage_lazy(lambda: PipelineStageResult(
            stage=PipelineStage.PROMPT_BUILD,
            input_data={
                "category": category,
                "user_question": user_question,
                "context": context,
                "recent_history": recent_history,
            },
            output_data={
                "system_message": system_message,
                "user_prompt": user_prompt,
                "prompt": messages,
            },
            metrics={
                "prompt_source": f"RAGSystem.answer:{category or 'default'}",
                "prompt_version": None,
                **(
                    {"prompt_hash": stable_hash(messages)}
                    if pipeline_hashes_enabled()
                    else {}
                ),
            },
            duration_ms=(time.perf_counter() - prompt_started) * 1000,
        ))

        # 3. Use vLLM's OpenAI API interface instead of local generation loop
        generation_started = time.perf_counter()
        settings = {
            "model": self.model_id,
            "max_tokens": max_new_tokens,
            "temperature": generation_temperature,
            "top_p": generation_top_p,
            "seed": generation_seed,
            "generation_temperature": generation_temperature,
            "generation_top_p": generation_top_p,
            "generation_seed": generation_seed,
        }
        try:
            response = await self._completion(
                model=self.model_id,
                messages=messages,
                max_tokens=max_new_tokens,
                temperature=generation_temperature,
                top_p=generation_top_p,
                seed=generation_seed,
            )
            answer = clean_llm_answer(response.choices[0].message.content)
        except Exception as exc:
            emit_pipeline_stage_lazy(lambda: PipelineStageResult(
                stage=PipelineStage.GENERATION,
                status="ERROR",
                input_data=(
                    {"prompt_hash": stable_hash(messages)}
                    if pipeline_hashes_enabled()
                    else {}
                ),
                metrics=settings,
                duration_ms=(time.perf_counter() - generation_started) * 1000,
                error_code=getattr(exc, "error_code", type(exc).__name__),
                error_data={"error_type": type(exc).__name__},
            ))
            raise
        emit_pipeline_stage_lazy(lambda: PipelineStageResult(
            stage=PipelineStage.GENERATION,
            input_data=(
                {"prompt_hash": stable_hash(messages)}
                if pipeline_hashes_enabled()
                else {}
            ),
            output_data={"answer": answer},
            metrics={
                **settings,
                **(
                    {"answer_hash": stable_hash(answer)}
                    if pipeline_hashes_enabled()
                    else {}
                ),
            },
            duration_ms=(time.perf_counter() - generation_started) * 1000,
        ))
        return answer


    async def generate_text(self, prompt):
        response = await self._completion(
            model=self.model_id,
            messages=[{"role": "system", "content": "You are a helpful assistant."},
                      {"role": "user", "content": prompt}],
            max_tokens=PERFORMANCE_SETTINGS.rag_rewrite_max_tokens,
            temperature=PERFORMANCE_SETTINGS.rag_rewrite_temperature,
            top_p=PERFORMANCE_SETTINGS.rag_rewrite_top_p,
            seed=PERFORMANCE_SETTINGS.rag_rewrite_seed,
        )
        return response.choices[0].message.content

    def save(self, path: str):
        """Save RAG system"""
        self.search_engine.save(path)

        # Save RAG-specific config
        config_path = Path(path) / "rag_config.json"
        config = {
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def load(self, path: str):
        """Load RAG system"""
        self.search_engine.load(path)

        # Load RAG-specific config
        config_path = Path(path) / "rag_config.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                self.chunk_size = config.get("chunk_size", 500)
                self.chunk_overlap = config.get("chunk_overlap", 50)
