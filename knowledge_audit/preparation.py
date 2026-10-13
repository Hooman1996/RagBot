"""Reuse production preparation components, never the full answering workflow."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import re

from conversation_history import format_rewrite_history, NO_CONVERSATION_HISTORY
from knowledge_audit.history import AuditHistoryProvider
from knowledge_audit.inputs import ImportedDataset, InputEvent
from knowledge_audit.privacy import AuditError, Redactor
from pipeline_observer import bind_pipeline_observer, PipelineStage
from utils.persian_normalization import normalize_persian_text
from utils.retrieval_query_canonicalizer import canonicalize_retrieval_query


# Conservative context uncertainty, not scope classification or gap detection.
_ELLIPTICAL = re.compile(
    r"\b(?:how long (?:does|will) it|what about (?:it|that)|that one|it takes)\b|"
    r"(?:چقدر|چه مدت|چند روز).*?(?:طول|زمان|وقت)|"
    r"^(?:چقدر طول می.?کشد|چند روزه|چقدر زمان می.?بره|پس چی|چطور|چگونه|چرا|"
    r"آن|اون|این|همون)(?:\s|[؟?]|$)", re.I)
_STOP = set("how long does will it take takes what about the a is to and چه چقدر مدت چند روز طول زمان وقت می کشد میکشد میبره برای از به و است آن اون این همون".split())


def context_dependent(query: str) -> bool:
    return bool(_ELLIPTICAL.search(query))


def grounded_rewrite(resolved: str, messages: tuple[dict, ...]) -> bool:
    """Conservative lexical evidence only; no semantic proof is claimed."""
    words = lambda text: set(re.findall(r"\w+", normalize_persian_text(text).lower())) - _STOP
    return bool(words(resolved) & words(" ".join(m["content"] for m in messages)))


class _RewriteMetadata:
    """Ignore content-bearing observer payloads; retain fixed rewrite provenance."""
    pipeline_hashes_enabled = False

    def __init__(self):
        self.fallback = False

    def record(self, result):
        if result.stage == PipelineStage.REWRITE:
            self.fallback = bool(result.metrics.get("fallback_used"))


@dataclass
class QueryPreparer:
    text_processor: object
    blocking_runner: object
    history_rewriting_service: object | None = None
    intent_classifier: object | None = None

    @classmethod
    def from_answering_service(cls, service):
        """Dashboard/runner can inject the exact active production components."""
        return cls(service.text_processor, service.blocking_runner,
                   service.history_rewriting_service, service.intent_classifier)

    async def prepare(self, event: InputEvent, history: AuditHistoryProvider,
                      redactor: Redactor, *, model_prepare: bool) -> dict:
        result = {"source_row_id": event.source_row_id, "source_record_ordinal": event.ordinal,
                  "source_query_id": event.source_query_ref, "safe_session_ref": event.safe_session_ref,
                  "timestamp": event.timestamp.isoformat() if event.timestamp else "",
                  "timestamp_status": event.timestamp_status, "timestamp_provenance": event.time_provenance,
                  "input_query_redacted": "", "normalized_query_redacted": "",
                  "standalone_query_redacted": "", "canonical_retrieval_query_redacted": "",
                  "existing_intent": "", "scope_status": "unknown", "processing_status": "preparation_only",
                  "coverage_status": "", "preparation_status": "pending_model", "model_prepared": False,
                  "rewrite_status": "not_run", "preparation_errors": [], "uncertainty_codes": list(event.issues)}
        try:
            original = redactor.text(event.content)
            result["input_query_redacted"] = original
            if any(i in event.issues for i in ("missing_query", "missing_message", "invalid_role", "invalid_record_width")):
                result.update(preparation_status="invalid_input", preparation_errors=list(event.issues))
                return result
            # Same order/strip rules as AnsweringService._answer. Redaction is an
            # audit boundary before external calls, with its effect recorded.
            normalized = await self.blocking_runner.run(self.text_processor.normalize, original.strip())
            normalized = normalize_persian_text(str(normalized).strip())
            if not normalized:
                raise AuditError("empty_normalized_query")
            result["normalized_query_redacted"] = redactor.text(normalized)
            context = history.before(event)
            result["history_provenance"] = context.provenance
            result["history_status"] = context.provenance["history_status"]
            if original != event.content:
                result["uncertainty_codes"].append("redaction_changed_query")
            dependent = context_dependent(normalized)
            if dependent and (not context.messages or context.provenance["prior_order_ambiguous"]):
                result.update(preparation_status="needs_context", rewrite_status="insufficient_context")
                result["uncertainty_codes"].append("unresolved_context")
                return result
            if not model_prepare:
                return result
            if self.intent_classifier is None or self.history_rewriting_service is None:
                raise AuditError("preparation_components_missing")
            rewritten = normalized
            formatted = format_rewrite_history(list(context.messages), max_turns=3)
            observer = _RewriteMetadata()
            # Suppress inherited terminal/evidence observers during all model
            # calls. Only fixed rewrite metadata is inspected in memory.
            with bind_pipeline_observer(observer):
                if formatted != NO_CONVERSATION_HISTORY:
                    response = await self.history_rewriting_service.rewrite_query(
                        current_query=normalized, current_summary=formatted)
                    rewritten = normalize_persian_text(str(response or "").strip()) or normalized
                    safe_rewrite = redactor.text(rewritten)
                    if safe_rewrite != rewritten:
                        result["uncertainty_codes"].append("redaction_changed_rewrite")
                    rewritten = safe_rewrite
                    result["rewrite_status"] = "fallback" if observer.fallback else "rewritten"
                else:
                    result["rewrite_status"] = "no_prior_history"
                classify = getattr(self.intent_classifier, "classify_detailed", None) or self.intent_classifier.classify
                classified = await classify(rewritten)
            intent = str(classified.get("type") or "general")
            result.update(model_prepared=True, existing_intent=intent,
                standalone_query_redacted=redactor.text(rewritten),
                canonical_retrieval_query_redacted=redactor.text(
                    canonicalize_retrieval_query(rewritten) if intent == "general" else rewritten),
                preparation_status="prepared")
            # General is not proof of bank/KB scope. No extra scope logic in A1.
            if intent == "chitchat":
                result["scope_status"] = "chitchat"
            if dependent and (observer.fallback or rewritten == normalized or
                              context_dependent(rewritten) or not grounded_rewrite(rewritten, context.messages[-6:])):
                result.update(preparation_status="needs_context", rewrite_status="unverified_context")
                result["uncertainty_codes"].append("unresolved_context")
            elif observer.fallback or context.provenance["prior_order_ambiguous"]:
                result["preparation_status"] = "uncertain_preparation"
            if any(code.startswith("redaction_changed") for code in result["uncertainty_codes"]) and result["preparation_status"] == "prepared":
                result["preparation_status"] = "uncertain_preparation"
        except Exception as exc:
            # Exception strings, repr, tracebacks and custom model error codes
            # can contain private text. Persist fixed allowlisted codes only.
            allowed = {"redaction_text_limit", "empty_normalized_query", "preparation_components_missing"}
            result.update(preparation_status="failed", preparation_errors=[
                str(exc) if isinstance(exc, AuditError) and str(exc) in allowed else "query_preparation_failed"])
        return result


async def prepare_dataset(dataset: ImportedDataset, preparer: QueryPreparer,
                          redactor: Redactor, *, model_limit: int = 0,
                          timeout_seconds: float = 50.0, progress=None) -> list[dict]:
    if isinstance(model_limit, bool) or not isinstance(model_limit, int) or not 0 <= model_limit <= 10:
        raise AuditError("invalid_model_sample_limit")
    if isinstance(timeout_seconds, bool) or not 0 < timeout_seconds <= 50:
        raise AuditError("invalid_preparation_timeout")
    history = AuditHistoryProvider(dataset, redactor)
    results, attempted = [], 0
    for processing_ordinal, event in enumerate(dataset.processing_order(), 1):
        model_prepare = attempted < model_limit
        if model_prepare:
            attempted += 1
        try:
            result = await asyncio.wait_for(preparer.prepare(event, history, redactor,
                model_prepare=model_prepare), timeout_seconds)
        except asyncio.TimeoutError:
            # Re-run only deterministic validation/normalization for a complete
            # row envelope; never retry model inference after a timeout.
            result = {"source_row_id": event.source_row_id, "source_record_ordinal": event.ordinal,
                      "preparation_status": "failed", "processing_status": "preparation_only",
                      "coverage_status": "", "preparation_errors": ["preparation_timeout"],
                      "model_prepared": False}
        result["processing_ordinal"] = processing_ordinal
        result["model_selected"] = model_prepare
        results.append(result)
        if progress:
            progress(processing_ordinal, len(dataset.selected))
    return sorted(results, key=lambda r: r["source_record_ordinal"])
