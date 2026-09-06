"""Capture effective, non-secret runtime settings for reproducibility."""

from __future__ import annotations

import hashlib
import inspect
import os
import subprocess
from pathlib import Path
from typing import Any

from utils.performance_config import PERFORMANCE_SETTINGS


def _sha(value: str | None) -> str | None:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else None


def git_commit_sha(repository_root: Path | None = None) -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repository_root,
            check=True, capture_output=True, text=True, timeout=3,
        ).stdout.strip()
    except Exception:
        return None


def build_config_snapshot(
    *, answering_service: Any | None = None, selected_documents: list[str] | None = None
) -> dict[str, Any]:
    rag = getattr(getattr(answering_service, "agent_service", None), "rag_system", None)
    search_engine = getattr(rag, "search_engine", None)
    classifier = getattr(answering_service, "intent_classifier", None)
    rewriter = getattr(answering_service, "history_rewriting_service", None)
    rewrite_prompt = getattr(getattr(rewriter, "config", None), "QUERY_REWRITE_PROMPT", None)
    try:
        answer_prompt_source = inspect.getsource(type(rag).answer) if rag is not None else None
    except (OSError, TypeError):
        answer_prompt_source = None
    return {
        "schema_version": "evaluation-config-v1",
        "intent": {
            "model_path_basename": getattr(classifier, "model_path_basename", None),
            "checkpoint_sha256": getattr(classifier, "checkpoint_sha256", None),
            "threshold": getattr(classifier, "threshold", None),
            "device": str(getattr(classifier, "device", "")) or None,
            "embedding_dimension": getattr(classifier, "embedding_dimension", None),
            "embedding_role": getattr(classifier, "embedding_role", None),
            "embedding_prompt_name": getattr(
                classifier, "embedding_prompt_name", None
            ),
        },
        "normalizer": {
            "identity": "PersianTextProcessor.normalize+normalize_persian_text",
            "version": None,
        },
        "rewrite": {
            "prompt_hash": _sha(rewrite_prompt), "prompt_version": None,
            "temperature": PERFORMANCE_SETTINGS.rag_rewrite_temperature,
            "top_p": PERFORMANCE_SETTINGS.rag_rewrite_top_p,
            "seed": PERFORMANCE_SETTINGS.rag_rewrite_seed,
            "max_tokens": PERFORMANCE_SETTINGS.rag_rewrite_max_tokens,
        },
        "embedding": {
            "model": os.getenv("EMBEDDING_MODEL"),
            "dimension": getattr(search_engine, "_expected_embedding_dimensions", 1024),
        },
        "retrieval": {
            "top_k": PERFORMANCE_SETTINGS.rag_retrieval_top_k,
            "candidate_limit": PERFORMANCE_SETTINGS.rag_semantic_candidate_limit,
            "qdrant_collection": getattr(
                search_engine,
                "collection_name",
                os.getenv("QDRANT_COLLECTION", "hihelp_embeddings"),
            ),
            "knowledge_sources": list(selected_documents or []),
        },
        "rerank": {
            "model": os.getenv("RERANKER_MODEL"),
            "enabled": PERFORMANCE_SETTINGS.rag_context_rerank_enabled,
            "top_k": PERFORMANCE_SETTINGS.rag_context_rerank_top_k,
            "scope": "answer_context",
            "raw_scores": False,
            "related_questions": {
                "threshold": (
                    PERFORMANCE_SETTINGS.rag_related_questions_rerank_threshold
                ),
                "scope": "faq_related_questions",
            },
        },
        "generation": {
            "model": getattr(rag, "model_id", os.getenv("LLM_MODEL")),
            "temperature": PERFORMANCE_SETTINGS.rag_answer_temperature,
            "top_p": PERFORMANCE_SETTINGS.rag_answer_top_p,
            "seed": PERFORMANCE_SETTINGS.rag_answer_seed,
            "max_tokens": PERFORMANCE_SETTINGS.rag_max_new_tokens,
            "chitchat_temperature": (
                PERFORMANCE_SETTINGS.rag_chitchat_temperature
            ),
            "chitchat_top_p": PERFORMANCE_SETTINGS.rag_chitchat_top_p,
            "chitchat_seed": PERFORMANCE_SETTINGS.rag_chitchat_seed,
            "chitchat_max_tokens": PERFORMANCE_SETTINGS.rag_chitchat_max_new_tokens,
            "prompt_version": None,
            "answer_prompt_source_hash": _sha(answer_prompt_source),
            "per_turn_prompt_hash_stage": "PROMPT_BUILD",
        },
        "git_commit_sha": git_commit_sha(Path(__file__).resolve().parents[4]),
    }
