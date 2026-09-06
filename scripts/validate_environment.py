#!/usr/bin/env python3
"""Validate RagBot environment files without revealing configuration values.

The application calls ``load_dotenv()`` with its default ``override=False``.
This validator mirrors that important precedence rule: an already exported
process variable wins over the selected dotenv file. It deliberately does not
import ``main`` or service configuration modules because those imports create
clients and may attempt network or database work.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import urlsplit


PLACEHOLDER_RE = re.compile(
    r"(?i)(change[-_ ]?me|replace[-_ ]?me|placeholder|example|"
    r"your[-_ ]|<[^>]+>|^x{3,}$)"
)
KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
LINE_RE = re.compile(
    r"^\s*(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=(?P<value>.*)$"
)
TRUE_VALUES = {"true", "1", "yes", "on"}
FALSE_VALUES = {"false", "0", "no", "off"}


@dataclass(frozen=True)
class VariableSpec:
    kind: str = "string"
    default: str | None = None
    required: tuple[str, ...] = ()
    secret: bool = False
    component: str = "FastAPI"
    restart: str = "FastAPI"
    deprecated: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    allowed: tuple[str, ...] = ()
    usage: str = "production runtime"


def _specs() -> dict[str, VariableSpec]:
    both = ("staging", "production")
    specs: dict[str, VariableSpec] = {
        # Application and direct Uvicorn entry point.
        "ENVIRONMENT": VariableSpec(
            allowed=("development", "staging", "production"),
            component="Unused metadata",
            restart="none (not consumed)",
            usage="apparently unused",
        ),
        "API_HOST": VariableSpec(
            default="0.0.0.0", component="Uvicorn", restart="FastAPI"
        ),
        "API_PORT": VariableSpec(
            kind="int",
            default="8080",
            minimum=1,
            maximum=65535,
            component="Uvicorn",
            restart="FastAPI",
        ),
        # Qdrant.
        "QDRANT_URL": VariableSpec(
            kind="url",
            component="Legacy vector layer",
            restart="legacy command only",
            deprecated="Active runtime uses QDRANT_HOST, QDRANT_PORT, and QDRANT_HTTPS.",
            usage="legacy or inactive",
        ),
        "QDRANT_HOST": VariableSpec(
            default="localhost", component="Qdrant", restart="FastAPI"
        ),
        "QDRANT_PORT": VariableSpec(
            kind="int",
            default="6333",
            minimum=1,
            maximum=65535,
            component="Qdrant",
            restart="FastAPI",
        ),
        "QDRANT_API_KEY": VariableSpec(
            required=("production",),
            secret=True,
            component="Qdrant",
            restart="FastAPI",
        ),
        "QDRANT_COLLECTION": VariableSpec(
            default="hihelp_embeddings", component="Qdrant", restart="FastAPI"
        ),
        "QDRANT_VECTOR_SIZE": VariableSpec(
            kind="int",
            default="1024",
            minimum=1,
            component="Qdrant/retrieval",
            restart="FastAPI and data insertion",
        ),
        "QDRANT_HTTPS": VariableSpec(
            kind="bool",
            default="false",
            component="Qdrant",
            restart="FastAPI",
        ),
        # PostgreSQL runtime and setup connection.
        "POSTGRES_HOST": VariableSpec(
            required=both, component="PostgreSQL", restart="FastAPI"
        ),
        "POSTGRES_PORT": VariableSpec(
            kind="int",
            default="5432",
            required=both,
            minimum=1,
            maximum=65535,
            component="PostgreSQL",
            restart="FastAPI",
        ),
        "POSTGRES_DB": VariableSpec(
            required=both, component="PostgreSQL", restart="FastAPI"
        ),
        "POSTGRES_USER": VariableSpec(
            required=both,
            secret=True,
            component="PostgreSQL",
            restart="FastAPI",
        ),
        "POSTGRES_PASSWORD": VariableSpec(
            required=both,
            secret=True,
            component="PostgreSQL",
            restart="FastAPI",
        ),
        "DEFAULT_DB_HOST": VariableSpec(
            required=(),
            component="Database setup",
            restart="setup_dbs.py only",
            usage="database setup",
        ),
        "DEFAULT_DB_PORT": VariableSpec(
            kind="int",
            minimum=1,
            maximum=65535,
            component="Database setup",
            restart="setup_dbs.py only",
            usage="database setup",
        ),
        "DEFAULT_DB_USER": VariableSpec(
            secret=True,
            component="Database setup",
            restart="setup_dbs.py only",
            usage="database setup",
        ),
        "DEFAULT_DB_PASSWORD": VariableSpec(
            secret=True,
            component="Database setup",
            restart="setup_dbs.py only",
            usage="database setup",
        ),
        "DEFAULT_DB_NAME": VariableSpec(
            component="Database setup",
            restart="setup_dbs.py only",
            usage="database setup",
        ),
        # MinIO.
        "MINIO_ENDPOINT": VariableSpec(
            default="localhost:9000", component="MinIO", restart="FastAPI"
        ),
        "MINIO_ACCESS_KEY": VariableSpec(
            required=both, secret=True, component="MinIO", restart="FastAPI"
        ),
        "MINIO_SECRET_KEY": VariableSpec(
            required=both, secret=True, component="MinIO", restart="FastAPI"
        ),
        "MINIO_SECURE": VariableSpec(
            kind="bool",
            default="false",
            component="MinIO/data insertion",
            restart="FastAPI or data-insertion command",
            usage="data insertion; ignored by active FastAPI Config",
        ),
        "MINIO_BUCKET": VariableSpec(
            required=both, component="MinIO", restart="FastAPI"
        ),
        # Model-serving and retrieval identity.
        "VLLM_URL": VariableSpec(
            kind="url",
            default="http://localhost:8000/v1",
            component="vLLM client",
            restart="FastAPI",
        ),
        "TEI_EMBED_URL": VariableSpec(
            kind="url",
            required=both,
            component="TEI embedding client",
            restart="FastAPI",
        ),
        "TEI_RERANK_URL": VariableSpec(
            kind="url",
            required=both,
            component="TEI reranker client",
            restart="FastAPI",
        ),
        "INTENT_CLASSIFIER_MODEL_PATH": VariableSpec(
            kind="path",
            required=both,
            component="Intent classifier",
            restart="FastAPI",
        ),
        "INTENT_CLASSIFIER_THRESHOLD": VariableSpec(
            kind="float",
            required=both,
            minimum=0.0000001,
            maximum=0.9999999,
            component="Intent classifier",
            restart="FastAPI",
        ),
        "INTENT_CLASSIFIER_DEVICE": VariableSpec(
            required=both,
            allowed=("cpu", "cuda"),
            component="Intent classifier",
            restart="FastAPI",
        ),
        "INTENT_CLASSIFIER_REQUIRED": VariableSpec(
            kind="bool",
            required=both,
            component="Intent classifier",
            restart="FastAPI",
        ),
        "INTENT_CLASSIFIER_EXPECTED_SHA256": VariableSpec(
            kind="sha256",
            required=both,
            component="Intent classifier",
            restart="FastAPI",
        ),
        "EMBEDDING_MODEL": VariableSpec(
            component="Legacy model metadata",
            restart="FastAPI",
            usage="loaded but behaviorally unused by TEI runtime",
        ),
        "EMBEDDING_MODEL_NAME": VariableSpec(
            component="Legacy embedding service",
            restart="legacy command only",
            deprecated="Use EMBEDDING_MODEL if the legacy local model path is revived.",
            usage="legacy or inactive",
        ),
        "LLM_MODEL": VariableSpec(
            component="Legacy model metadata",
            restart="none (not consumed after loading)",
            usage="loaded but behaviorally unused",
        ),
        "RERANKER_MODEL": VariableSpec(
            component="Legacy model metadata",
            restart="none (local reranker code is commented out)",
            usage="loaded but behaviorally unused",
        ),
        # Data tools.
        "KNOWLEDGE_BASE_CSV": VariableSpec(
            kind="path",
            component="Knowledge preparation",
            restart="hihelp_knowledge_changer.py only",
            usage="development only",
        ),
        "DATA_INSERTION_DIRECTORY": VariableSpec(
            kind="path",
            component="Data insertion",
            restart="data-insertion command only",
            usage="data insertion",
        ),
        # Application-side timeout and concurrency settings.
        "APPLICATION_REQUEST_TIMEOUT_SECONDS": VariableSpec(
            kind="float",
            default="50",
            minimum=0.000001,
            maximum=50,
            component="FastAPI deadline",
            restart="FastAPI",
        ),
        "REQUEST_CONCURRENCY_LIMIT": VariableSpec(
            kind="int",
            default="32",
            minimum=1,
            component="FastAPI admission",
            restart="FastAPI",
        ),
        "REQUEST_ADMISSION_TIMEOUT_SECONDS": VariableSpec(
            kind="float",
            default="12",
            minimum=0.000001,
            component="FastAPI admission",
            restart="FastAPI",
        ),
        "BLOCKING_CONCURRENCY_LIMIT": VariableSpec(
            kind="int",
            default="16",
            minimum=1,
            component="FastAPI blocking runner",
            restart="FastAPI",
        ),
        "TEI_HTTP_MAX_CONNECTIONS": VariableSpec(
            kind="int", default="32", minimum=1, component="TEI client", restart="FastAPI"
        ),
        "TEI_HTTP_MAX_KEEPALIVE_CONNECTIONS": VariableSpec(
            kind="int", default="16", minimum=1, component="TEI client", restart="FastAPI"
        ),
        "TEI_HTTP_KEEPALIVE_EXPIRY_SECONDS": VariableSpec(
            kind="float", default="30", minimum=0.000001, component="TEI client", restart="FastAPI"
        ),
        "TEI_HTTP_CONNECT_TIMEOUT_SECONDS": VariableSpec(
            kind="float", default="3", minimum=0.000001, component="TEI client", restart="FastAPI"
        ),
        "TEI_HTTP_READ_TIMEOUT_SECONDS": VariableSpec(
            kind="float", default="15", minimum=0.000001, component="TEI client", restart="FastAPI"
        ),
        "TEI_HTTP_WRITE_TIMEOUT_SECONDS": VariableSpec(
            kind="float", default="5", minimum=0.000001, component="TEI client", restart="FastAPI"
        ),
        "TEI_HTTP_POOL_TIMEOUT_SECONDS": VariableSpec(
            kind="float", default="3", minimum=0.000001, component="TEI client", restart="FastAPI"
        ),
        "TEI_EMBED_INSERT_BATCH_SIZE": VariableSpec(
            kind="int",
            default="32",
            minimum=1,
            component="Data insertion/TEI",
            restart="data-insertion command only",
            usage="data insertion",
        ),
        "TEI_EMBED_MAX_CLIENT_BATCH_SIZE": VariableSpec(
            kind="int",
            default="50",
            minimum=1,
            component="Data insertion/TEI policy",
            restart="FastAPI or data-insertion command",
        ),
        "VLLM_HTTP_MAX_CONNECTIONS": VariableSpec(
            kind="int", default="32", minimum=1, component="vLLM client", restart="FastAPI"
        ),
        "VLLM_HTTP_MAX_KEEPALIVE_CONNECTIONS": VariableSpec(
            kind="int", default="16", minimum=1, component="vLLM client", restart="FastAPI"
        ),
        "VLLM_HTTP_KEEPALIVE_EXPIRY_SECONDS": VariableSpec(
            kind="float", default="30", minimum=0.000001, component="vLLM client", restart="FastAPI"
        ),
        "VLLM_HTTP_CONNECT_TIMEOUT_SECONDS": VariableSpec(
            kind="float", default="3", minimum=0.000001, component="vLLM client", restart="FastAPI"
        ),
        "VLLM_HTTP_READ_TIMEOUT_SECONDS": VariableSpec(
            kind="float", default="45", minimum=0.000001, component="vLLM client", restart="FastAPI"
        ),
        "VLLM_HTTP_WRITE_TIMEOUT_SECONDS": VariableSpec(
            kind="float", default="5", minimum=0.000001, component="vLLM client", restart="FastAPI"
        ),
        "VLLM_HTTP_POOL_TIMEOUT_SECONDS": VariableSpec(
            kind="float", default="3", minimum=0.000001, component="vLLM client", restart="FastAPI"
        ),
        "QDRANT_CONCURRENCY": VariableSpec(
            kind="int", default="4", minimum=1, component="Qdrant client", restart="FastAPI"
        ),
        "RAG_QUERY_CANONICALIZATION_ENABLED": VariableSpec(
            kind="bool",
            default="true",
            required=both,
            component="Retrieval query preparation",
            restart="FastAPI",
        ),
        "RAG_RETRIEVAL_TOP_K": VariableSpec(
            kind="int", default="10", minimum=1, component="Retrieval", restart="FastAPI"
        ),
        "RAG_SEMANTIC_CANDIDATE_LIMIT": VariableSpec(
            kind="int", default="50", minimum=1, component="Retrieval", restart="FastAPI"
        ),
        "RAG_RELATED_QUESTIONS_RERANK_THRESHOLD": VariableSpec(
            kind="float", default="0.1", minimum=0, maximum=1, component="Retrieval", restart="FastAPI"
        ),
        "MOBILE_RELATED_QUESTIONS_RERANK_THRESHOLD": VariableSpec(
            kind="float", default="0.5", minimum=0, maximum=1, component="Mobile API", restart="FastAPI"
        ),
        "RAG_MAX_NEW_TOKENS": VariableSpec(
            kind="int", default="500", minimum=1, component="vLLM generation", restart="FastAPI"
        ),
        "RAG_CHITCHAT_MAX_NEW_TOKENS": VariableSpec(
            kind="int", default="200", minimum=1, component="vLLM generation", restart="FastAPI"
        ),
        "RAG_REWRITE_MAX_TOKENS": VariableSpec(
            kind="int", default="1000", minimum=1, component="vLLM generation", restart="FastAPI"
        ),
        # Inactive SQLAlchemy pool.
        "SQLALCHEMY_POOL_SIZE": VariableSpec(
            kind="int", default="5", minimum=1, component="Legacy SQLAlchemy pool", restart="legacy command only", usage="legacy or inactive"
        ),
        "SQLALCHEMY_MAX_OVERFLOW": VariableSpec(
            kind="int", default="10", minimum=0, component="Legacy SQLAlchemy pool", restart="legacy command only", usage="legacy or inactive"
        ),
        "SQLALCHEMY_POOL_TIMEOUT": VariableSpec(
            kind="int", default="30", minimum=1, component="Legacy SQLAlchemy pool", restart="legacy command only", usage="legacy or inactive"
        ),
        "SQLALCHEMY_POOL_RECYCLE": VariableSpec(
            kind="int", default="3600", minimum=1, component="Legacy SQLAlchemy pool", restart="legacy command only", usage="legacy or inactive"
        ),
        "SQLALCHEMY_ECHO": VariableSpec(
            kind="bool", default="false", component="Legacy SQLAlchemy pool", restart="legacy command only", usage="legacy or inactive"
        ),
        # Staging load-test metadata and authentication.
        "RAGBOT_STAGING_AUTH_TOKEN": VariableSpec(
            secret=True, component="Load test", restart="load-test script only", usage="load testing"
        ),
        "RAGBOT_STAGING_LIMITER_CAPACITY": VariableSpec(
            component="Load-test report metadata", restart="load-test script only", usage="load testing"
        ),
        "RAGBOT_STAGING_GPU_INFO": VariableSpec(
            component="Load-test report metadata", restart="load-test script only", usage="load testing"
        ),
        "RAGBOT_VLLM_IMAGE": VariableSpec(
            component="Load-test report metadata", restart="load-test script only", usage="load testing"
        ),
        "RAGBOT_TEI_EMBED_IMAGE": VariableSpec(
            component="Load-test report metadata", restart="load-test script only", usage="load testing"
        ),
        "RAGBOT_TEI_RERANK_IMAGE": VariableSpec(
            component="Load-test report metadata", restart="load-test script only", usage="load testing"
        ),
    }
    return specs


SPECS = _specs()

OVERLAP_GROUPS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "qdrant address",
        ("QDRANT_URL", "QDRANT_HOST", "QDRANT_PORT", "QDRANT_HTTPS"),
        "Active runtime ignores QDRANT_URL and builds the address from split fields.",
    ),
    (
        "PostgreSQL roles",
        (
            "POSTGRES_HOST",
            "POSTGRES_PORT",
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "DEFAULT_DB_HOST",
            "DEFAULT_DB_PORT",
            "DEFAULT_DB_NAME",
            "DEFAULT_DB_USER",
            "DEFAULT_DB_PASSWORD",
        ),
        "POSTGRES_* is the target database; DEFAULT_DB_* is only the administrative setup connection.",
    ),
    (
        "embedding model aliases",
        ("EMBEDDING_MODEL", "EMBEDDING_MODEL_NAME"),
        "The names belong to different, mostly inactive local-model implementations.",
    ),
    (
        "request timeouts",
        (
            "APPLICATION_REQUEST_TIMEOUT_SECONDS",
            "REQUEST_ADMISSION_TIMEOUT_SECONDS",
            "TEI_HTTP_CONNECT_TIMEOUT_SECONDS",
            "TEI_HTTP_READ_TIMEOUT_SECONDS",
            "TEI_HTTP_WRITE_TIMEOUT_SECONDS",
            "TEI_HTTP_POOL_TIMEOUT_SECONDS",
            "VLLM_HTTP_CONNECT_TIMEOUT_SECONDS",
            "VLLM_HTTP_READ_TIMEOUT_SECONDS",
            "VLLM_HTTP_WRITE_TIMEOUT_SECONDS",
            "VLLM_HTTP_POOL_TIMEOUT_SECONDS",
        ),
        "These protect different layers; downstream work must fit inside the total deadline.",
    ),
    (
        "concurrency and pools",
        (
            "REQUEST_CONCURRENCY_LIMIT",
            "BLOCKING_CONCURRENCY_LIMIT",
            "TEI_HTTP_MAX_CONNECTIONS",
            "TEI_HTTP_MAX_KEEPALIVE_CONNECTIONS",
            "VLLM_HTTP_MAX_CONNECTIONS",
            "VLLM_HTTP_MAX_KEEPALIVE_CONNECTIONS",
            "QDRANT_CONCURRENCY",
            "SQLALCHEMY_POOL_SIZE",
            "SQLALCHEMY_MAX_OVERFLOW",
        ),
        "Each limit applies at a different queue or resource boundary.",
    ),
    (
        "TEI insertion batches",
        ("TEI_EMBED_INSERT_BATCH_SIZE", "TEI_EMBED_MAX_CLIENT_BATCH_SIZE"),
        "The insertion batch must not exceed the client-side maximum.",
    ),
)


@dataclass(frozen=True)
class ParsedEnvironment:
    values: dict[str, str]
    errors: tuple[str, ...]


def _strip_inline_comment(value: str) -> str:
    """Strip an unquoted dotenv comment while preserving quoted hashes."""
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote == '"':
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            continue
        if char == "#" and quote is None and (
            index == 0 or value[index - 1].isspace()
        ):
            return value[:index].rstrip()
    return value.strip()


def _decode_value(raw: str, line_number: int) -> tuple[str | None, str | None]:
    value = _strip_inline_comment(raw)
    if not value:
        return "", None
    if value[0] in {"'", '"'}:
        quote = value[0]
        if len(value) < 2 or value[-1] != quote:
            return None, f"line {line_number}: unterminated quoted value"
        body = value[1:-1]
        if quote == '"':
            body = (
                body.replace(r"\n", "\n")
                .replace(r"\r", "\r")
                .replace(r"\t", "\t")
                .replace(r"\"", '"')
                .replace(r"\\", "\\")
            )
        return body, None
    return value, None


def parse_env_file(path: Path) -> ParsedEnvironment:
    values: dict[str, str] = {}
    errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return ParsedEnvironment({}, (f"cannot read environment file: {exc}",))
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = LINE_RE.match(line)
        if not match:
            errors.append(f"line {line_number}: invalid dotenv assignment")
            continue
        key = match.group("key")
        value, error = _decode_value(match.group("value"), line_number)
        if error:
            errors.append(error)
            continue
        if key in values:
            errors.append(f"line {line_number}: duplicate variable {key}")
        values[key] = value or ""
    return ParsedEnvironment(values, tuple(errors))


def _validate_value(name: str, value: str, spec: VariableSpec) -> str | None:
    try:
        if spec.kind == "int":
            parsed: float = int(value)
        elif spec.kind == "float":
            parsed = float(value)
        elif spec.kind == "bool":
            normalized = value.strip().lower()
            if normalized not in TRUE_VALUES | FALSE_VALUES:
                return "must be a boolean: true/false, 1/0, yes/no, or on/off"
            parsed = 1 if normalized in TRUE_VALUES else 0
        elif spec.kind == "url":
            parts = urlsplit(value)
            if parts.scheme not in {"http", "https"} or not parts.hostname:
                return "must be an http:// or https:// URL with a host"
            if parts.username is not None or parts.password is not None:
                return "must not contain embedded credentials"
            parsed = 0
        elif spec.kind == "path":
            if "\x00" in value:
                return "must be a valid file-system path"
            parsed = 0
        elif spec.kind == "sha256":
            if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
                return "must be a 64-character hexadecimal SHA256"
            parsed = 0
        else:
            parsed = 0
    except (TypeError, ValueError):
        return f"must be a valid {spec.kind}"

    if spec.allowed and value.strip().lower() not in spec.allowed:
        return "must be one of: " + ", ".join(spec.allowed)
    if spec.minimum is not None and parsed < spec.minimum:
        return f"must be at least {spec.minimum:g}"
    if spec.maximum is not None and parsed > spec.maximum:
        return f"must not exceed {spec.maximum:g}"
    return None


def analyze_environment(
    path: Path,
    mode: str,
    *,
    show_optional: bool = False,
    process_environment: Mapping[str, str] | None = None,
) -> dict[str, object]:
    parsed = parse_env_file(path)
    process = os.environ if process_environment is None else process_environment
    effective = dict(parsed.values)
    sources = {name: "env file" for name in parsed.values}
    for name in SPECS:
        if name in process:
            effective[name] = process[name]
            sources[name] = "process environment"

    findings: list[dict[str, str]] = [
        {"severity": "critical", "variable": "(syntax)", "message": error}
        for error in parsed.errors
    ]
    variable_rows: list[dict[str, object]] = []

    for name, spec in SPECS.items():
        present = name in effective
        value = effective.get(name, "")
        required = mode in spec.required
        if present and value == "":
            status = "empty"
        elif present and PLACEHOLDER_RE.search(value):
            status = "placeholder"
        elif present:
            error = _validate_value(name, value, spec)
            status = "malformed" if error else "set"
            if error:
                findings.append(
                    {"severity": "critical", "variable": name, "message": error}
                )
        elif spec.default is not None:
            status = "defaulted"
        else:
            status = "missing"

        if required and status in {"missing", "empty", "placeholder"}:
            findings.append(
                {
                    "severity": "critical",
                    "variable": name,
                    "message": f"is required in {mode} mode but is {status}",
                }
            )
        if spec.deprecated and present:
            findings.append(
                {
                    "severity": "warning",
                    "variable": name,
                    "message": f"deprecated: {spec.deprecated}",
                }
            )
        if (
            status == "placeholder"
            and not required
            and spec.secret
        ):
            findings.append(
                {
                    "severity": "warning",
                    "variable": name,
                    "message": "contains a placeholder and cannot authenticate",
                }
            )

        if show_optional or required or present or status == "malformed":
            variable_rows.append(
                {
                    "name": name,
                    "status": status,
                    "required": required,
                    "secret": spec.secret,
                    "component": spec.component,
                    "restart_required": spec.restart,
                    "source": sources.get(name, "code default" if spec.default else "none"),
                }
            )

    unknown = sorted(name for name in parsed.values if name not in SPECS)
    for name in unknown:
        findings.append(
            {
                "severity": "warning",
                "variable": name,
                "message": "unknown variable: no repository consumer was found",
            }
        )
        variable_rows.append(
            {
                "name": name,
                "status": "unknown",
                "required": False,
                "secret": True,
                "component": "unknown",
                "restart_required": "unknown",
                "source": "env file",
            }
        )

    overlaps: list[dict[str, object]] = []
    for group_name, names, explanation in OVERLAP_GROUPS:
        configured = [name for name in names if name in effective and effective[name] != ""]
        if len(configured) >= 2:
            overlaps.append(
                {
                    "group": group_name,
                    "variables": configured,
                    "message": explanation,
                }
            )
            findings.append(
                {
                    "severity": "informational",
                    "variable": ", ".join(configured),
                    "message": f"overlap ({group_name}): {explanation}",
                }
            )

    def add_relationship_error(variable: str, message: str) -> None:
        findings.append(
            {"severity": "critical", "variable": variable, "message": message}
        )

    def as_number(name: str) -> float | None:
        value = effective.get(name)
        if value is None or _validate_value(name, value, SPECS[name]):
            return None
        return float(value)

    tei_keepalive = as_number("TEI_HTTP_MAX_KEEPALIVE_CONNECTIONS")
    tei_connections = as_number("TEI_HTTP_MAX_CONNECTIONS")
    if (
        tei_keepalive is not None
        and tei_connections is not None
        and tei_keepalive > tei_connections
    ):
        add_relationship_error(
            "TEI_HTTP_MAX_KEEPALIVE_CONNECTIONS",
            "cannot exceed TEI_HTTP_MAX_CONNECTIONS",
        )
    vllm_keepalive = as_number("VLLM_HTTP_MAX_KEEPALIVE_CONNECTIONS")
    vllm_connections = as_number("VLLM_HTTP_MAX_CONNECTIONS")
    if (
        vllm_keepalive is not None
        and vllm_connections is not None
        and vllm_keepalive > vllm_connections
    ):
        add_relationship_error(
            "VLLM_HTTP_MAX_KEEPALIVE_CONNECTIONS",
            "cannot exceed VLLM_HTTP_MAX_CONNECTIONS",
        )
    insertion_batch = as_number("TEI_EMBED_INSERT_BATCH_SIZE")
    max_batch = as_number("TEI_EMBED_MAX_CLIENT_BATCH_SIZE")
    if (
        insertion_batch is not None
        and max_batch is not None
        and insertion_batch > max_batch
    ):
        add_relationship_error(
            "TEI_EMBED_INSERT_BATCH_SIZE",
            "cannot exceed TEI_EMBED_MAX_CLIENT_BATCH_SIZE",
        )
    top_k = as_number("RAG_RETRIEVAL_TOP_K")
    candidate_limit = as_number("RAG_SEMANTIC_CANDIDATE_LIMIT")
    if (
        top_k is not None
        and candidate_limit is not None
        and top_k > candidate_limit
    ):
        add_relationship_error(
            "RAG_RETRIEVAL_TOP_K",
            "cannot exceed RAG_SEMANTIC_CANDIDATE_LIMIT",
        )

    severity_counts = {
        severity: sum(1 for item in findings if item["severity"] == severity)
        for severity in ("critical", "warning", "informational")
    }
    return {
        "env_file": str(path),
        "mode": mode,
        "summary": {
            "known_variables": len(SPECS),
            "variables_in_file": len(parsed.values),
            "unknown_variables": len(unknown),
            "overlap_groups": len(overlaps),
            **severity_counts,
        },
        "variables": sorted(variable_rows, key=lambda row: str(row["name"])),
        "findings": findings,
        "overlaps": overlaps,
    }


def render_text(report: Mapping[str, object]) -> str:
    summary = report["summary"]
    assert isinstance(summary, Mapping)
    lines = [
        f"Environment validation ({report['mode']} mode)",
        f"File: {report['env_file']}",
        (
            "Summary: "
            f"{summary['critical']} critical, {summary['warning']} warning, "
            f"{summary['informational']} informational"
        ),
        "",
        "Variables (values are intentionally omitted):",
    ]
    variables = report["variables"]
    assert isinstance(variables, list)
    for row in variables:
        assert isinstance(row, Mapping)
        flags = ["required" if row["required"] else "optional"]
        if row["secret"]:
            flags.append("secret")
        lines.append(
            f"- {row['name']}: {row['status']} "
            f"({', '.join(flags)}; restart: {row['restart_required']})"
        )
    findings = report["findings"]
    assert isinstance(findings, list)
    if findings:
        lines.extend(("", "Findings:"))
        for finding in findings:
            assert isinstance(finding, Mapping)
            lines.append(
                f"- [{str(finding['severity']).upper()}] "
                f"{finding['variable']}: {finding['message']}"
            )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a RagBot dotenv file without printing values."
    )
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--mode", choices=("staging", "production"), required=True)
    parser.add_argument("--show-optional", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = analyze_environment(
        args.env_file,
        args.mode,
        show_optional=args.show_optional,
    )
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_text(report))
    summary = report["summary"]
    assert isinstance(summary, Mapping)
    return 2 if int(summary["critical"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
