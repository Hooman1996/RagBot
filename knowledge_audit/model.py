"""Sequential structured model calls with served chat-template token accounting."""
from __future__ import annotations
import asyncio
import time
import os
import json
from datetime import datetime, timezone

from pydantic import ValidationError
from knowledge_audit.privacy import AuditError, Redactor
from knowledge_audit.prompts import messages
from knowledge_audit.schemas import SCHEMAS
from pipeline_observer import bind_pipeline_observer
from utils.concurrency import run_with_limit
from utils.performance_config import PERFORMANCE_SETTINGS
from knowledge_audit.failures import VERSION as FAILURE_VERSION, category, safe_correlation
from utils.read_only_audit import canonical_sha256
from utils.audit_dispatch import audit_dispatch, completion_metadata, current_audit

DIAGNOSTIC_TYPES = frozenset({"json_invalid", "missing", "literal_error", "extra_forbidden", "string_type",
    "string_pattern_mismatch", "string_too_short", "string_too_long", "int_type", "int_parsing",
    "greater_than_equal", "less_than_equal", "list_type", "too_short", "too_long", "bool_type",
    "dict_type", "value_error", "model_type", "none_required"})


def schema_version(role, schemas=SCHEMAS):
    return schemas[role].model_fields["version"].annotation.__args__[0]


def validation_diagnostics(error, role, stage, metric, schemas=SCHEMAS):
    """Never include values, messages, contexts, URLs or arbitrary field names."""
    schema = schemas[role].model_json_schema()
    fields = set(schema.get("properties", {}))
    for definition in schema.get("$defs", {}).values():
        fields.update(definition.get("properties", {}))
    return [{"responsibility": role, "schema_version": schema_version(role, schemas), "stage": stage,
             "field_path": [part if isinstance(part, str) and part in fields else "*" for part in item["loc"]],
             "error_type": item["type"] if item["type"] in DIAGNOSTIC_TYPES else "validation_error",
             "prompt_tokens": metric["prompt_tokens"], "completion_tokens": metric["completion_tokens"],
             "finish_reason": metric.get("finish_reason", "unknown")}
            for item in error.errors(include_url=False, include_context=False, include_input=False)[:20]]


def json_syntax_summary(value):
    """Content-free parser position/category; never retain error messages."""
    if not isinstance(value, str):
        return {"category": "not_text"}
    try:
        json.loads(value)
        return {"category": "valid_json"}
    except json.JSONDecodeError as error:
        categories = {"Expecting value": "expected_value", "Expecting ',' delimiter": "missing_comma",
                      "Expecting property name enclosed in double quotes": "unquoted_property",
                      "Extra data": "trailing_content", "Invalid \\escape": "invalid_escape",
                      "Invalid control character at": "invalid_control"}
        return {"category": categories.get(error.msg, "json_syntax"), "position": error.pos,
                "at_end": error.pos >= len(value.rstrip()), "starts_object": value.lstrip().startswith("{")}


class AuditModel:
    def __init__(self, rag, http, origin, settings, redactor: Redactor, *, limiter=None,
                 schemas=None, message_builder=None, identity_fields=()):
        self.rag, self.http, self.origin = rag, http, origin.rstrip("/").removesuffix("/v1")
        self.settings, self.redactor, self.limiter = settings, redactor, limiter
        self.context_limit = None
        self.serving = {}
        self.metrics = []
        self.progress_callback = None
        self.metrics_path = None
        self.call_sequence = 0
        self.request_journal = None
        self.schemas = SCHEMAS if schemas is None else schemas
        self.message_builder = messages if message_builder is None else message_builder
        self.identity_fields = frozenset(identity_fields)

    async def discover(self):
        models = await audit_dispatch('metadata',lambda:self.http.get(self.origin + '/v1/models'))
        models.raise_for_status()
        served = [m for m in models.json()["data"] if m["id"] == self.rag.model_id]
        if len(served) != 1 or type(served[0].get("max_model_len")) is not int or served[0]["max_model_len"] <= 0:
            raise AuditError("unverified_context_limit")
        version = await audit_dispatch('metadata',lambda:self.http.get(self.origin + '/version'))
        version.raise_for_status()
        self.context_limit = served[0]["max_model_len"]
        self.serving = {"served_model_id": self.redactor.opaque("model", self.rag.model_id),
                        "max_model_len": self.context_limit, "serving_version": self.redactor.text(version.json()["version"]),
                        "token_count_method": "served_tokenize_messages_chat_template",
                        "weights_tokenizer_revision": "unverified",
                        "structured_output_mode": "json_schema_strict_1"}

    async def count_completion_tokens(self,metadata):
        # Rewrite calls use the same served chat-template counter as audit calls.
        response=await audit_dispatch('tokenization',lambda:self.http.post(self.origin+'/tokenize',
            json={'model':metadata['model'],'messages':metadata['messages'],'add_generation_prompt':True}))
        response.raise_for_status();count=response.json().get('count')
        if type(count) is not int or count<1:raise AuditError('invalid_token_count')
        return count

    async def count(self, role, data):
        if self.context_limit is None:
            raise AuditError("model_not_discovered")
        msg = self.message_builder(role, data)
        response = await audit_dispatch('tokenization',lambda:self.http.post(self.origin + "/tokenize", json={"model": self.rag.model_id,
            "messages": msg, "add_generation_prompt": True}))
        response.raise_for_status()
        tokens = response.json().get("count")
        if type(tokens) is not int or tokens < 1:
            raise AuditError("invalid_token_count")
        return tokens, msg

    async def fits(self, role, data):
        tokens, _ = await self.count(role, data)
        return tokens + self.settings.model_max_tokens + self.settings.token_margin <= self.context_limit

    async def call(self, role, data, *, purpose="evaluation"):
        self.call_sequence += 1
        call_id = self.call_sequence
        for attempt in (1, 2):
            try:
                return await self._call_once(role, data, purpose=purpose, call_id=call_id, attempt=attempt)
            except AuditError as error:
                last = self.metrics[-1]
                recoverable = str(error) == "invalid_model_schema" and last.get("finish_reason") == "stop" and any(
                    d["stage"] == "before_redaction" and d["error_type"] == "json_invalid" for d in last["validation_diagnostics"])
                if attempt == 2 or not recoverable:
                    raise
                # One fresh, identically constrained request; no repair/coercion,
                # no semantic/citation/redaction/length/network retry.

    async def _call_once(self, role, data, *, purpose, call_id, attempt):
        started = time.perf_counter()
        phase = "progress"
        phase_started = started
        metric = {"role": role, "responsibility": role, "schema_version": schema_version(role, self.schemas),
                  "started_at": datetime.now(timezone.utc).isoformat(),
                  "call_id": call_id, "attempt": attempt, "maximum_attempts": 2,
                  "recovery_policy": "json-invalid-stop-one-fresh-response-1",
                  "purpose": purpose, "status": "error", "prompt_tokens": None, "finish_reason": "not_returned",
                  "validation_diagnostics": [],
                  "reserved_output_tokens": self.settings.model_max_tokens,
                  "context_limit": self.context_limit, "completion_tokens": None,
                  "failure_policy": FAILURE_VERSION, "failure_category": "none", "dispatched": False,
                  "phase_timings_ms": {}, "boundary": "progress",
                  "payload_sha256": canonical_sha256(data),
                  "evaluation_phase": getattr(self, "evaluation_phase", "unknown") if getattr(self, "evaluation_phase", "unknown")
                      in {"production", "initial", "broader", "question", "unknown"} else "unknown"}
        def enter(next_phase):
            nonlocal phase, phase_started
            metric["phase_timings_ms"][phase] = round((time.perf_counter() - phase_started) * 1000, 3)
            phase, phase_started = next_phase, time.perf_counter()
            metric["boundary"] = phase
        try:
            if self.progress_callback:
                await self.progress_callback(role)
            enter("tokenization")
            tokens, msg = await self.count(role, data)
            metric["prompt_tokens"] = tokens
            metric["messages_sha256"] = canonical_sha256(msg)
            if tokens + self.settings.model_max_tokens + self.settings.token_margin > self.context_limit:
                metric["status"] = "token_overflow"
                raise AuditError("model_input_token_overflow")
            async def operation():
                enter("completion")
                async def mark_dispatch():
                    if self.request_journal:
                        await self.request_journal("dispatched", metric)
                    metric["dispatched"] = True
                if current_audit() is None:
                    await mark_dispatch()
                with bind_pipeline_observer(None), completion_metadata(role,tokens,mark_dispatch):
                    return await self.rag._completion(model=self.rag.model_id, messages=msg,
                        max_tokens=self.settings.model_max_tokens, temperature=0, top_p=1, seed=42,
                        response_format={"type": "json_schema", "json_schema": {"name": role + "_" + schema_version(role, self.schemas).replace("-", "_"),
                            "strict": True, "schema": self.schemas[role].model_json_schema()}})
            enter("admission")
            deadline = asyncio.timeout(PERFORMANCE_SETTINGS.application_request_timeout_seconds)
            try:
                async with deadline:
                    response = await (run_with_limit(self.limiter, operation,
                        acquire_timeout=PERFORMANCE_SETTINGS.request_admission_timeout_seconds) if self.limiter else operation())
            except TimeoutError:
                if deadline.expired():
                    raise AuditError("outer_operation_deadline") from None
                raise
            metric.update(safe_correlation(response, self.redactor))
            metric["server_completion_state"] = "response_received"
            if self.request_journal:
                await self.request_journal("response_received", metric)
            enter("validation")
            choice = response.choices[0]
            metric["completion_tokens"] = response.usage.completion_tokens
            metric["server_prompt_tokens"] = response.usage.prompt_tokens
            metric["content_characters"] = len(choice.message.content) if isinstance(choice.message.content, str) else 0
            metric["reasoning_characters"] = max([len(v) for v in (
                getattr(choice.message, "reasoning", None), getattr(choice.message, "reasoning_content", None)) if isinstance(v, str)] or [0])
            reasoning = getattr(getattr(response.usage, "completion_tokens_details", None), "reasoning_tokens", None)
            metric["reasoning_tokens"] = reasoning if type(reasoning) is int else None
            metric["finish_reason"] = choice.finish_reason if choice.finish_reason in {"stop", "length", "content_filter", "tool_calls", "function_call"} else "unknown"
            if response.usage.prompt_tokens != tokens:
                raise AuditError("token_count_serving_mismatch")
            if choice.finish_reason != "stop":
                raise AuditError("incomplete_structured_output")
            # Strict local JSON/schema checks remain mandatory even with server
            # JSON grammar. No parser repair or free-text fallback. The wrapper
            # permits only the versioned, single JSON-syntax recovery attempt.
            stage = "before_redaction"
            result = self.schemas[role].model_validate_json(choice.message.content)
            stage = "after_redaction"
            safe = self._safe(result.model_dump())
            result = self.schemas[role].model_validate(safe)
            metric["status"] = "validated"
            return result.model_dump()
        except ValidationError as error:
            metric["failure_category"] = "schema_validation"
            metric["validation_diagnostics"] = validation_diagnostics(error, role, stage, metric, self.schemas)
            if stage == "before_redaction":
                metric["json_syntax"] = json_syntax_summary(choice.message.content)
            raise AuditError("invalid_model_schema") from None
        except asyncio.CancelledError:
            metric.update(status="cancelled", failure_category="cancellation")
            raise
        except Exception as error:
            code = category(error)
            if code == "dispatch_budget_exhausted":
                metric.update(dispatched=False, status="blocked")
            metric["failure_category"] = "output_length" if metric["finish_reason"] == "length" else code
            metric.update(safe_correlation(error, self.redactor))
            if isinstance(error, AuditError):
                raise
            raise AuditError(code) from None
        finally:
            metric.setdefault("server_completion_state", "unknown" if metric["dispatched"] else "not_dispatched")
            metric["phase_timings_ms"][phase] = round((time.perf_counter() - phase_started) * 1000, 3)
            metric["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
            self.metrics.append(metric)
            budget=current_audit()
            if budget and metric['dispatched'] and metric.get('server_completion_state')=='response_received':
                await budget.io(budget.model_result,metric['failure_category'])
            if self.request_journal:
                await self.request_journal("unknown" if metric["server_completion_state"] == "unknown" else
                    "response_received" if metric["dispatched"] else "failed_before_dispatch", metric)
            if self.metrics_path:
                from utils.read_only_audit import canonical_json
                fd = os.open(self.metrics_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(canonical_json(metric) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())

    async def check_schema_support(self):
        """Five sequential synthetic probes; bounded syntax recovery is counted."""
        from knowledge_audit.evidence import EvidenceIndex
        from utils.read_only_audit import canonical_sha256
        records = [{"chunk_id": "synthetic-1", "faq_entry_id": "synthetic-1", "question": "Imaginary approval duration?",
                    "answer": "Approval takes two days.", "document_title": "Synthetic_FAQ", "main_category": "Synthetic",
                    "sub_category": "Synthetic", "redaction_changed": False}]
        records[0]["content_sha256"] = canonical_sha256(records[0])
        snap = {"snapshot_id": canonical_sha256(records), "records": records}
        entry = EvidenceIndex(snap).entry("synthetic-1")
        aspects = [{"aspect_id": "a1", "description": "Approval duration", "conditions": []}]
        support = {"aspect_id": "a1", "entry_id": "synthetic-1", "support_id": "synthetic_support",
            "citations": [{"snapshot_id": snap["snapshot_id"], "faq_entry_id": "synthetic-1", "chunk_id": "synthetic-1", "sentence_number": 1}],
            "applicability": "applicable", "conditions": [], "dependencies": [], "explanation": "Synthetic duration sentence."}
        proof = {"question": "Imaginary approval duration?", "aspects": aspects, "supports": [support],
                 "source_evidence": [entry], "observed_conflicts": []}
        probes = {"scope": {"question": "How can I replace a card?", "preceding_history": []},
                  "aspects": {"question": "Imaginary approval duration?"},
                  "batch": {"question": "Imaginary approval duration?", "aspects": aspects, "entries": [entry]},
                  "reconciliation": proof, "verification": proof}
        result = {"version": "schema-capability-1", "mode": "json_schema_strict_1", "roles": {}}
        for role, data in probes.items():
            await self.call(role, data, purpose="schema_capability")
            result["roles"][role] = {"schema_version": schema_version(role), "status": "validated"}
        return result

    def _safe(self, value, key=""):
        if isinstance(value, dict):
            return {k: self._safe(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [self._safe(v, key) for v in value]
        if isinstance(value, str) and key not in {"snapshot_id", "chunk_id", "faq_entry_id", "entry_id", "aspect_id", "support_ids"} | self.identity_fields:
            return self.redactor.text(value)
        return value
