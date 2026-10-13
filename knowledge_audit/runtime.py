"""Local component wiring only. Does not start FastAPI or initialize data stores."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

from knowledge_audit.privacy import AuditError

ROOT = Path(__file__).resolve().parents[1]


def confirm_staging(*, confirmed: bool, model: bool = False, snapshot: bool = False) -> None:
    """Restrict CLI live work to the documented confirmed local staging targets.

    Historical reports establish this root .env's development targets. Explicit
    assertion alone never permits arbitrary remote production configuration.
    """
    from dotenv import dotenv_values
    if not confirmed:
        raise AuditError("staging_confirmation_required")
    file_values = dotenv_values(ROOT / ".env")
    keys = (["TEI_EMBED_URL", "VLLM_URL"] if model else []) + (["POSTGRES_HOST", "QDRANT_HOST"] if snapshot else [])
    for key in keys:
        value = os.environ.get(key, "")
        host = urlsplit(value).hostname if "URL" in key else value
        if value != file_values.get(key) or host not in {"127.0.0.1", "localhost", "::1"}:
            raise AuditError("unconfirmed_service_target")


def code_identity() -> dict:
    paths = [*sorted(ROOT.glob("knowledge_audit/*.py")), ROOT / "scripts/knowledge_audit_prepare.py",
             *[ROOT / p for p in ("answering_service.py", "conversation_history.py", "intent_classifier.py",
                "intent_classifier_factory.py", "new_architecture/app/config.py",
                "new_architecture/app/services/history/rewriting.py", "utils/RagSystem.py",
                "utils/persian_hybrid_search.py", "utils/persian_normalization.py", "utils/log_sanitizer.py",
                "utils/retrieval_query_canonicalizer.py", "utils/tei_embedding_client.py", "scripts/kb_signature.py")]]
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, check=True, text=True).stdout.strip()
    return {"git_head": head, "file_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def configuration_identity(policy, model_limit: int, redactor) -> dict:
    from utils.performance_config import PERFORMANCE_SETTINGS
    from utils.retrieval_query_canonicalizer import RETRIEVAL_QUERY_ALIASES_SHA256
    from intent_classifier_factory import load_intent_classifier_config
    config = load_intent_classifier_config()
    checkpoint = Path(config.model_path)
    return {"performance": asdict(PERFORMANCE_SETTINGS), "timestamp_policy": asdict(policy),
            "model_limit": model_limit, "model_sample_rule": "first_n_chronological_selected_rows",
            "audit_concurrency": 1, "state_message_limit": 10, "rewrite_max_turns": 3,
            "redaction_version": redactor.version, "alias_sha256": RETRIEVAL_QUERY_ALIASES_SHA256,
            "classifier": {"threshold": config.threshold, "device": config.device, "required": config.required,
                "expected_sha256": config.expected_sha256,
                "actual_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest() if checkpoint.is_file() else None},
            "service_target_identities": {k: redactor.opaque("endpoint", os.environ.get(k, "")) for k in
                ("TEI_EMBED_URL", "VLLM_URL", "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "QDRANT_HOST", "QDRANT_PORT", "QDRANT_COLLECTION")}}


async def serving_identity(http, redactor) -> dict:
    result = {}
    for key, suffix in (("TEI_EMBED_URL", "/info"), ("VLLM_URL", "/models")):
        response = await http.get(os.environ[key].rstrip("/") + suffix)
        response.raise_for_status()
        body = response.json()
        if key == "VLLM_URL":
            result[key] = [{"model_id_hash": redactor.opaque("served_model", r["id"]),
                            "max_model_len": r.get("max_model_len")} for r in body["data"]]
        else:
            result[key] = {"model_id_hash": redactor.opaque("served_model", body["model_id"]),
                           **{k: body.get(k) for k in ("version", "max_input_length", "auto_truncate", "max_client_batch_size")}}
    response = await http.get(os.environ["VLLM_URL"].rstrip("/").removesuffix("/v1") + "/version")
    response.raise_for_status()
    result["vllm_version"] = redactor.text(str(response.json().get("version", "unknown")))
    result["immutable_weight_tokenizer_revisions"] = "unverified"
    return result


async def live_components(runner, http):
    from utils.RagSystem import RAGSystem
    from new_architecture.app.services.history.rewriting import HistoryRewritingService
    from intent_classifier_factory import build_intent_classifier
    # Construction opens no data-store connection; only rewrite/embedding methods
    # are used. RAG's retrieval/generation answer methods are never invoked.
    rag = await runner.run(RAGSystem, qdrant_client=None, blocking_runner=runner,
                           tei_http_client=http)
    rag.audit_call_counts = {"embedding_posts": 0, "rewrite_completions": 0}
    original_completion = rag._completion
    original_encode = rag.search_engine._encode_query
    async def completion(**kwargs):
        rag.audit_call_counts["rewrite_completions"] += 1
        return await original_completion(**kwargs)
    async def encode(query):
        rag.audit_call_counts["embedding_posts"] += 1
        return await original_encode(query)
    rag._completion = completion
    try:
        classifier = await runner.run(build_intent_classifier,
            embedding_model=encode, blocking_runner=runner,
            scenarios_path=str(ROOT / "scenarios.json"))
        return rag, HistoryRewritingService(rag, None), classifier
    except BaseException:
        await rag.aclose()
        raise
