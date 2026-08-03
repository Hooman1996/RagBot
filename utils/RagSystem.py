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
from langchain_classic.chains import RetrievalQA

from dotenv import load_dotenv
load_dotenv()

# 1. Replace Hugging Face & Torch imports with the OpenAI client
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
import httpx
from utils.concurrency import BoundedBlockingRunner
from utils.performance_config import PERFORMANCE_SETTINGS
from utils.service_errors import (
    ServiceTimeoutError,
    ServiceUnavailableError,
)
from .rag_utils import clean_llm_answer

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

        self.qdrant_client = qdrant_client
        self.chunk_fetcher = chunk_fetcher
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
        try:
            return await self.client.chat.completions.create(**kwargs)
        except APITimeoutError as exc:
            raise ServiceTimeoutError("Language model service timed out") from exc
        except (APIConnectionError, APIStatusError) as exc:
            raise ServiceUnavailableError(
                "Language model service is unavailable"
            ) from exc

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
        sorted_results = sorted(results, key=lambda x: x.score, reverse=True)
        formatted_documents = []

        for index, result in enumerate(sorted_results, start=1):
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
               temperature=1,
               # temperature = 0,
               enable_history=True, category=None):

        max_new_tokens = (
            max_new_tokens or PERFORMANCE_SETTINGS.rag_max_new_tokens
        )
        if category == "chitchat":
            max_new_tokens = PERFORMANCE_SETTINGS.rag_chitchat_max_new_tokens

            self.template = """You are a warm, professional, and highly polite AI assistant for Karafarin Bank (بانک کارآفرین) and Hi Bank (های بانک). 
            The user is currently engaging in casual conversation (chit-chat) rather than asking a specific banking question.

            <rules>
            1. Respond in a friendly, respectful, and professional Persian tone (لحن محترمانه، صمیمی و حرفه‌ای).
            2. Acknowledge their message warmly.
            3. Briefly introduce yourself as the Karafarin Bank / Hi Bank AI assistant.
            4. Politely ask how you can assist them with their banking or application needs today.
            5. Keep the response concise and avoid giving any factual banking information since the user didn't ask for it.
            </rules>

            <history>
            {current_history}
            </history>

            <user_message>
            {question}
            </user_message>

            Your Response (Persian):
            """
            prompt = self.template.format(
                current_history=recent_history,
                question=user_question
            )

        elif category == "ابلاغیه ها" or category == "قرارداد ها":
            self.template = """You are an elite AI Banking Analyst for Karafarin Bank (بانک کارآفرین) and Hi Bank (های بانک). Your target audience consists of Bank Managers and Executives. 
            Your sole task is to answer the user's question based STRICTLY and EXCLUSIVELY on the provided document chunks.

            <rules>
            1. ZERO HALLUCINATION (CRITICAL): You must not use any outside knowledge or conclude ideas that are not explicitly stated in the text. Treat the `<context>` as the absolute boundary of your knowledge.
            2. REFUSAL PROTOCOL: If the `<context>` does not contain the necessary information to confidently answer the `<question>`, your final output MUST be exactly: "متأسفانه اطلاعات مربوط به این پرسش در مستندات فعلی یافت نشد." Do not attempt to partially answer if the core information is missing.
            3. EXACT REFERENCES: Build your answer using the exact terminology, legal constraints, and numerical values found in the chunks. If chunks have titles or identifiers, weave them into your explanation to prove your source.
            4. MANAGERIAL TONE: The response must be in highly formal, professional, and precise standard Persian (کاملاً رسمی، اداری و مستند).
            5. CHAIN OF THOUGHT: You must first use a `<thought_process>` block to extract the relevant facts from the `<context>` and map them to the `<question>`. 
            6. OUTPUT CONSTRAINT: Output ONLY your analysis inside `<thought_process>`, followed strictly by the final Persian response inside `<answer>`.
            </rules>

            <context>
            {current_context}
            </context>

            <history>
            {current_history}
            </history>

            <question>
            {current_question}
            </question>
        """
            prompt = self.template.format(
                current_context=context,
                current_history=recent_history,
                current_question=user_question
            )

        else:
            self.template = """
            You are a high-precision corporate banking assistant operating exclusively within the core knowledge boundaries of *Karafarin Bank* (بانک کارآفرین) and the *Hi Bank* (های بانک) mobile ecosystem. Your performance is evaluated under a zero-tolerance rubric for hallucinations, out-of-scope compliance leakage, or conversational bloat.

    <system_directives>
    1. OPERATIONAL KNOWLEDGE ISOLATION: Evaluate the user query strictly against the data provided inside the <context> tag block. If the required solution, factual data point, phone number, or technical path is not explicitly documented within an <answer> tag inside the context, you must immediately abort your normal completion and output exactly: "متاسفانه اطلاعات دقیقی در این زمینه ندارم. لطفا با پشتیبانی تماس بگیرید."
    2. ZERO FLUFF / IMMEDIATE SOLUTION (CRITICAL): Absolutely no conversational preambles, summaries, conversational meta-commentary, or introductory acknowledgments are permitted. Do not echo or rephrase the question. Do not say "در پاسخ به سوال شما" or "سوال شما در مورد... است". Immediately follow the opening token with the direct factual execution.
    3. CONTEXT DECONVOLUTION & DEDUPLICATION: Multiple document blocks may feature overlapping procedures, URLs, or support lines (e.g., 02123350). You must synthesize these into a single, cohesive, non-repetitive response. Never state the same point, step, or phone number twice in the final output string.
    4. SCOPE BOUNDING & TARGET SEGMENTATION: Enforce semantic strictness on entities. If the <user_question> targets an "account" (حساب), do not serve, interpolate, or volunteer information pertaining to "cards" (کارت) or "credentials" unless they are explicitly co-located in the matching context node. If the query focuses on a "blockage/freeze" (مسدودی), do not slide into "deactivation" (غیرفعال‌سازی) unless it represents an identical resolution path in the data.
    5. DISCRETE XML OUTPUT BAN: Under no circumstances should any XML tags from the source context (such as <doc>, <question>, <answer>, etc.) leak into your final text output. The response must be rendered in clean, fully plaintext Persian prose.
    6. PERSISTENT SALUTATION CONSTRAINT: Prefix your final completion string with the formal token "کاربر گرامی، " exactly once. 
    7. CHIT-CHAT AND META-QUERIES: If the user submits a pure conversational greeting ("سلام"), or a query probing your identity, provide a single, ultra-short, polite sentence identifying yourself as the banking assistant, and request their specific task.
    </system_directives>

    <context>
    {formatted_search_results}
    </context>

    <user_question>
    {question}
    </user_question>

    [Instruction: Execute the direct solution now with maximum brevity, absolute precision, and zero introductory text]
    Your Plaintext Answer (Persian):
    """
            prompt = self.template.format(
                formatted_search_results=context,
                question=user_question
            )


        # print("*" * 100)
        # print("Final Context: ", prompt)
        # print("*" * 100)

        # print("*" * 100)
        # print("Search Results: ", context)
        # print("*" * 100)


        # 3. Use vLLM's OpenAI API interface instead of local generation loop
        response = await self._completion(
            model=self.model_id,
            messages=[{"role": "system", "content": "You are a helpful assistant."},
                      {"role": "user", "content": prompt}],
            max_tokens=max_new_tokens, temperature=temperature, top_p=0.95,
        )
        return clean_llm_answer(response.choices[0].message.content)


    async def generate_text(self, prompt):
        response = await self._completion(
            model=self.model_id,
            messages=[{"role": "system", "content": "You are a helpful assistant."},
                      {"role": "user", "content": prompt}],
            max_tokens=PERFORMANCE_SETTINGS.rag_rewrite_max_tokens,
            temperature=0.0,
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
