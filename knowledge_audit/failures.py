"""Allowlisted audit failure taxonomy. Never serialize exception representations."""
import asyncio

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError

from knowledge_audit.privacy import AuditError
from utils.service_errors import (ModelContextLengthError, ServiceOverloadedError,
    ServiceProtocolError, ServiceTimeoutError, ServiceUnavailableError)

VERSION = "audit-failures-1"
TRANSPORT_CODES = frozenset({"admission_timeout", "outer_operation_deadline", "model_read_timeout",
    "model_connect_timeout", "model_write_timeout", "model_pool_timeout", "model_timeout_unknown",
    "model_connection_failure", "model_service_failure", "model_http_rejection", "model_protocol_rejection"})
VALIDATION_CODES = frozenset({"invalid_model_schema", "invalid_citation", "invalid_evidence_support",
    "invalid_full_claim", "invalid_aspect_identity", "invalid_reconciliation_identity", "invalid_conflict_identity",
    "incomplete_structured_output", "model_input_token_overflow", "token_count_serving_mismatch"})
# Refusals before a run exists; never a row failure category.
RUN_ADMISSION_CODES = frozenset({"snapshot_policy_superseded"})


def causes(error):
    seen = set()
    while error is not None and id(error) not in seen and len(seen) < 12:
        seen.add(id(error))
        yield error
        error = getattr(error, "__cause__", None) or getattr(error, "__context__", None)


def category(error):
    chain = list(causes(error))
    if isinstance(error, asyncio.CancelledError):
        return "cancellation"
    # Specific transport cause takes priority over translated service errors.
    for kind, code in ((httpx.ReadTimeout, "model_read_timeout"), (httpx.ConnectTimeout, "model_connect_timeout"),
                       (httpx.WriteTimeout, "model_write_timeout"), (httpx.PoolTimeout, "model_pool_timeout")):
        if any(isinstance(e, kind) for e in chain):
            return code
    if isinstance(error, AuditError) and str(error) in TRANSPORT_CODES | VALIDATION_CODES:
        return str(error)
    if isinstance(error, AuditError) and str(error) == "diagnostic_budget_exhausted":
        return "dispatch_budget_exhausted"
    if any(isinstance(e, ServiceOverloadedError) for e in chain):
        return "admission_timeout"
    if any(isinstance(e, (ServiceTimeoutError, APITimeoutError, httpx.TimeoutException, TimeoutError)) for e in chain):
        return "model_timeout_unknown"
    if any(isinstance(e, ModelContextLengthError) for e in chain):
        return "model_input_token_overflow"
    if any(isinstance(e, (APIStatusError, httpx.HTTPStatusError)) for e in chain):
        return "model_http_rejection"
    if any(isinstance(e, (httpx.ProtocolError, ServiceProtocolError)) for e in chain):
        return "model_protocol_rejection"
    if any(isinstance(e, (httpx.ConnectError, APIConnectionError, ConnectionError)) for e in chain):
        return "model_connection_failure"
    if any(isinstance(e, ServiceUnavailableError) for e in chain):
        return "model_service_failure"
    return "audit_failed"


def safe_correlation(error_or_response, redactor):
    """Only numeric HTTP status and keyed opaque request ID; no headers/body."""
    result = {}
    for item in causes(error_or_response):
        status = getattr(item, "status_code", None)
        if type(status) is int and 100 <= status <= 599:
            result["http_status"] = status
        request_id = getattr(item, "_request_id", None) or getattr(item, "request_id", None)
        if isinstance(request_id, str) and request_id:
            result["server_request_ref"] = redactor.opaque("request", request_id)
            break
    return result
