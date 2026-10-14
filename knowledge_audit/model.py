"""Sequential structured model calls with served chat-template token accounting."""
from __future__ import annotations
import asyncio
import time
import os

from pydantic import ValidationError
from knowledge_audit.privacy import AuditError, Redactor
from knowledge_audit.prompts import messages
from knowledge_audit.schemas import SCHEMAS
from pipeline_observer import bind_pipeline_observer
from utils.concurrency import run_with_limit
from utils.performance_config import PERFORMANCE_SETTINGS


class AuditModel:
    def __init__(self, rag, http, origin, settings, redactor: Redactor, *, limiter=None):
        self.rag, self.http, self.origin = rag, http, origin.rstrip("/").removesuffix("/v1")
        self.settings, self.redactor, self.limiter = settings, redactor, limiter
        self.context_limit = None
        self.serving = {}
        self.metrics = []
        self.progress_callback = None
        self.metrics_path = None

    async def discover(self):
        models = await self.http.get(self.origin + "/v1/models")
        models.raise_for_status()
        served = [m for m in models.json()["data"] if m["id"] == self.rag.model_id]
        if len(served) != 1 or type(served[0].get("max_model_len")) is not int or served[0]["max_model_len"] <= 0:
            raise AuditError("unverified_context_limit")
        version = await self.http.get(self.origin + "/version")
        version.raise_for_status()
        self.context_limit = served[0]["max_model_len"]
        self.serving = {"served_model_id": self.redactor.opaque("model", self.rag.model_id),
                        "max_model_len": self.context_limit, "serving_version": self.redactor.text(version.json()["version"]),
                        "token_count_method": "served_tokenize_messages_chat_template",
                        "weights_tokenizer_revision": "unverified"}

    async def count(self, role, data):
        if self.context_limit is None:
            raise AuditError("model_not_discovered")
        msg = messages(role, data)
        response = await self.http.post(self.origin + "/tokenize", json={"model": self.rag.model_id,
            "messages": msg, "add_generation_prompt": True})
        response.raise_for_status()
        tokens = response.json().get("count")
        if type(tokens) is not int or tokens < 1:
            raise AuditError("invalid_token_count")
        return tokens, msg

    async def fits(self, role, data):
        tokens, _ = await self.count(role, data)
        return tokens + self.settings.model_max_tokens + self.settings.token_margin <= self.context_limit

    async def call(self, role, data):
        if self.progress_callback:
            await self.progress_callback(role)
        started = time.perf_counter()
        metric = {"role": role, "status": "error", "prompt_tokens": None,
                  "reserved_output_tokens": self.settings.model_max_tokens,
                  "context_limit": self.context_limit, "completion_tokens": None}
        try:
            tokens, msg = await self.count(role, data)
            metric["prompt_tokens"] = tokens
            if tokens + self.settings.model_max_tokens + self.settings.token_margin > self.context_limit:
                metric["status"] = "token_overflow"
                raise AuditError("model_input_token_overflow")
            async def operation():
                with bind_pipeline_observer(None):
                    return await self.rag._completion(model=self.rag.model_id, messages=msg,
                        max_tokens=self.settings.model_max_tokens, temperature=0, top_p=1, seed=42,
                        response_format={"type": "json_object"})
            response = await asyncio.wait_for(run_with_limit(self.limiter, operation,
                acquire_timeout=PERFORMANCE_SETTINGS.request_admission_timeout_seconds) if self.limiter else operation(),
                PERFORMANCE_SETTINGS.application_request_timeout_seconds)
            choice = response.choices[0]
            metric["completion_tokens"] = response.usage.completion_tokens
            metric["server_prompt_tokens"] = response.usage.prompt_tokens
            if response.usage.prompt_tokens != tokens:
                raise AuditError("token_count_serving_mismatch")
            if choice.finish_reason != "stop":
                raise AuditError("incomplete_structured_output")
            # Strict local JSON/schema checks remain mandatory even with server
            # JSON grammar. No parser repair, retries or free-text fallback.
            result = SCHEMAS[role].model_validate_json(choice.message.content)
            safe = self._safe(result.model_dump())
            result = SCHEMAS[role].model_validate(safe)
            metric["status"] = "validated"
            return result.model_dump()
        except ValidationError:
            raise AuditError("invalid_model_schema") from None
        finally:
            metric["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
            self.metrics.append(metric)
            if self.metrics_path:
                from utils.read_only_audit import canonical_json
                fd = os.open(self.metrics_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(canonical_json(metric) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())

    def _safe(self, value, key=""):
        if isinstance(value, dict):
            return {k: self._safe(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [self._safe(v, key) for v in value]
        if isinstance(value, str) and key not in {"snapshot_id", "chunk_id", "faq_entry_id", "entry_id", "aspect_id", "support_ids"}:
            return self.redactor.text(value)
        return value
