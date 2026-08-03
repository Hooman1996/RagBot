#!/usr/bin/env python3
"""Staging-only asynchronous load generator for POST /v1/talk.

The module deliberately depends only on the standard library and httpx. It
never retries and requires a fixture of operator-reserved staging identities
because this repository cannot guarantee collision-free generated national
codes. Synthetic request and response content is recorded in full.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import ipaddress
import json
import math
import os
import platform
import random
import socket
import statistics
import subprocess
import sys
import time
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

EXIT_PASS = 0
EXIT_ACCEPTANCE_FAILURE = 1
EXIT_SETUP_FAILURE = 2
DEFAULT_ENDPOINT = "/v1/talk"
SOURCE_LIMITER_CAPACITY = "32 (source default; live value unknown)"
SOURCE_STAGING_GPU = "NVIDIA RTX 5880 Ada Generation 48 GB (repository fact; live state unknown)"

SUCCESS = "success"
LIMITER_REJECTION = "limiter_acquire_timeout"
APPLICATION_DEADLINE = "application_deadline_timeout"
CLIENT_READ_TIMEOUT = "client_read_timeout"
CLIENT_CONNECT_TIMEOUT = "client_connect_timeout"
CLIENT_WRITE_TIMEOUT = "client_write_timeout"
POOL_TIMEOUT = "connection_pool_timeout"
DNS_FAILURE = "dns_failure"
CONNECTION_ERROR = "connection_error"
HTTP_4XX = "http_4xx"
HTTP_5XX = "http_5xx"
INVALID_SCHEMA = "invalid_response_schema"
UNEXPECTED_HTTP_STATUS = "unexpected_http_status"
CANCELLATION = "cancellation"
UNEXPECTED = "unexpected_exception"

FIELD_NAMES = [
    "run_id",
    "timestamp",
    "wave_number",
    "virtual_user_id",
    "virtual_user_number",
    "request_number",
    "scenario_id",
    "scenario",
    "session_id",
    "national_code",
    "national_code_hash",
    "query_text",
    "answer_text",
    "answer_character_count",
    "answer_word_count",
    "answer_is_empty",
    "response_schema_valid",
    "latency_ms",
    "success",
    "failure_category",
    "error_message",
    "response_byte_count",
    "request_start_timestamp",
    "request_end_timestamp",
    "start_perf_counter_ns",
    "end_perf_counter_ns",
    "client_elapsed_ms",
    "intended_start_perf_counter_ns",
    "scheduler_lag_ms",
    "http_status",
    "failure_class",
    "response_bytes",
    "answer_characters",
    "server_request_id",
    "server_timing",
    "server_timing_values",
    "limiter_wait_ms",
    "endpoint_processing_ms",
    "rewrite_duration_ms",
    "embedding_duration_ms",
    "qdrant_duration_ms",
    "reranker_duration_ms",
    "vllm_duration_ms",
    "timeout_category",
    "exception_type",
    "sanitized_error",
]


class SetupError(ValueError):
    """Invalid or unsafe benchmark configuration."""


@dataclass(frozen=True)
class Identity:
    alias: str
    national_code: str = field(repr=False)
    session_id: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class ScenarioStep:
    name: str
    query: str = field(repr=False)
    documents: tuple[str, ...] = ("General_FAQ",)


@dataclass(frozen=True)
class VirtualUser:
    number: int
    identity: Identity
    session_id: str


@dataclass(frozen=True)
class AcceptanceCriteria:
    minimum_success_rate: float = 0.99
    maximum_p95_ms: float = 20_000.0
    maximum_success_latency_ms: float = 20_000.0
    maximum_application_deadline_timeouts: int = 0
    maximum_limiter_rejections: int = 0
    maximum_http_5xx: int = 0
    strict: bool = False


@dataclass
class Config:
    base_url: str
    endpoint: str = DEFAULT_ENDPOINT
    concurrency: int = 50
    repetitions: int = 5
    request_timeout: float = 55.0
    connect_timeout: float = 5.0
    write_timeout: float = 10.0
    pool_timeout: float = 5.0
    acquire_start_delay: float = 0.05
    scenario: str = "faq"
    input_file: Path | None = None
    scenario_file: Path | None = None
    output_dir: Path | None = None
    seed: int = 20260728
    auth_token: str | None = field(default=None, repr=False)
    verify_tls: bool = True
    allow_http: bool = False
    warmup_requests: int = 0
    session_prefix: str = "ragbot-load"
    national_code_mode: str = "fixture"
    cleanup: bool = False
    workload_mode: str = "burst"
    arrival_rate: float | None = None
    max_connections: int = 100
    max_keepalive_connections: int = 50
    criteria: AcceptanceCriteria = field(default_factory=AcceptanceCriteria)

    @property
    def total_requests(self) -> int:
        return self.concurrency * self.repetitions


@dataclass
class RequestRecord:
    run_id: str
    wave_number: int
    virtual_user_number: int
    request_number: int
    scenario: str
    session_id: str
    national_code: str
    national_code_hash: str
    query_text: str
    request_start_timestamp: str
    request_end_timestamp: str
    start_perf_counter_ns: int
    end_perf_counter_ns: int
    client_elapsed_ms: float
    intended_start_perf_counter_ns: int | None = None
    scheduler_lag_ms: float | None = None
    http_status: int | None = None
    failure_class: str = UNEXPECTED
    response_bytes: int = 0
    answer_characters: int = 0
    answer_text: str = ""
    answer_word_count: int = 0
    answer_is_empty: bool = True
    response_schema_valid: bool = False
    server_request_id: str | None = None
    server_timing: str | None = None
    server_timing_values: dict[str, str | float] = field(default_factory=dict)
    limiter_wait_ms: float | None = None
    endpoint_processing_ms: float | None = None
    rewrite_duration_ms: float | None = None
    embedding_duration_ms: float | None = None
    qdrant_duration_ms: float | None = None
    reranker_duration_ms: float | None = None
    vllm_duration_ms: float | None = None
    timeout_category: str | None = None
    exception_type: str | None = None
    sanitized_error: str | None = None

    @property
    def success(self) -> bool:
        return self.failure_class == SUCCESS

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result.update(
            {
                "timestamp": self.request_start_timestamp,
                "virtual_user_id": self.virtual_user_number,
                "scenario_id": self.scenario,
                "answer_character_count": self.answer_characters,
                "latency_ms": self.client_elapsed_ms,
                "success": self.success,
                "failure_category": self.failure_class,
                "error_message": self.sanitized_error,
                "response_byte_count": self.response_bytes,
            }
        )
        return result

    def to_csv_dict(self) -> dict[str, Any]:
        result = self.to_dict()
        result["server_timing_values"] = json.dumps(
            self.server_timing_values, ensure_ascii=False, sort_keys=True
        )
        return result


BUILTIN_SCENARIOS: dict[str, tuple[ScenarioStep, ...]] = {
    "smoke": (
        ScenarioStep("smoke", "سلام، خوبی؟"),
    ),
    "chitchat": (
        ScenarioStep("chitchat", "سلام، خوبی؟"),
    ),
    "faq": (
        ScenarioStep(
            "faq",
            "آیا امکان افتتاح حساب مشترک به صورت غیرحضوری وجود دارد؟",
        ),
    ),
    "short": (
        ScenarioStep(
            "short",
            "آیا امکان افتتاح حساب مشترک به صورت غیرحضوری وجود دارد؟",
        ),
    ),
    "long": (
        ScenarioStep(
            "long",
            "شرایط افتتاح حساب جاری چیست و آیا این فرآیند به صورت غیرحضوری امکان پذیر است؟",
        ),
    ),
    "follow-up": (
        ScenarioStep(
            "follow-up-initial",
            "سقف انتقال وجه روزانه از طریق خدمات بانکی چقدر است؟",
        ),
        ScenarioStep(
            "follow-up-second",
            "سقف انتقال از طریق پل چقدر است؟",
        ),
    ),
    "mixed": (
        ScenarioStep("mixed-chitchat", "سلام، خوبی؟"),
        ScenarioStep(
            "mixed-faq",
            "آیا امکان افتتاح حساب مشترک به صورت غیرحضوری وجود دارد؟",
        ),
        ScenarioStep(
            "mixed-long",
            "شرایط افتتاح حساب جاری چیست و آیا این فرآیند به صورت غیرحضوری امکان پذیر است؟",
        ),
    ),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def percentile(values: Sequence[float], percent: float) -> float | None:
    """Return an R-7/NumPy-style linearly interpolated percentile."""

    if not values:
        return None
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction)


def is_valid_iranian_national_code(value: str) -> bool:
    """Validate the common 10-digit Iranian national-code checksum.

    This validator is provided for fixture auditing only. The load generator
    never generates checksum-valid identities because collision freedom cannot
    be guaranteed in this application.
    """

    if len(value) != 10 or not value.isdigit() or len(set(value)) == 1:
        return False
    check = int(value[-1])
    total = sum(int(value[index]) * (10 - index) for index in range(9))
    remainder = total % 11
    expected = remainder if remainder < 2 else 11 - remainder
    return check == expected


def national_code_hash(national_code: str, run_id: str) -> str:
    digest = hashlib.sha256(f"{run_id}:{national_code}".encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def deterministic_session_id(seed: int, prefix: str, virtual_user: int) -> str:
    namespace = uuid.uuid5(uuid.NAMESPACE_URL, f"ragbot-staging:{seed}:{prefix}")
    return str(uuid.uuid5(namespace, f"virtual-user:{virtual_user}"))


def calculate_total_requests(concurrency: int, repetitions: int) -> int:
    if concurrency < 1 or repetitions < 1:
        raise SetupError("concurrency and repetitions must both be at least 1")
    return concurrency * repetitions


def load_fixture(
    path: Path,
) -> tuple[list[Identity], dict[str, tuple[ScenarioStep, ...]]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupError(f"cannot read staging identity fixture: {type(exc).__name__}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("identities"), list):
        raise SetupError("input fixture must contain an identities array")

    identities: list[Identity] = []
    seen_aliases: set[str] = set()
    seen_codes: set[str] = set()
    seen_sessions: set[str] = set()
    for index, raw in enumerate(data["identities"], start=1):
        if not isinstance(raw, dict):
            raise SetupError(f"identity {index} must be an object")
        alias = raw.get("alias")
        code = raw.get("national_code")
        session_id = raw.get("session_id")
        if not isinstance(alias, str) or not alias.strip():
            raise SetupError(f"identity {index} has an invalid alias")
        if not isinstance(code, str) or not code or len(code) > 20:
            raise SetupError(f"identity {index} has an invalid national_code")
        if session_id is not None:
            if not isinstance(session_id, str):
                raise SetupError(f"identity {index} has an invalid session_id")
            try:
                parsed_session = uuid.UUID(session_id)
            except ValueError as exc:
                raise SetupError(
                    f"identity {index} session_id must be a UUID"
                ) from exc
            if str(parsed_session) != session_id:
                raise SetupError(
                    f"identity {index} session_id must be a canonical UUID"
                )
        if alias in seen_aliases or code in seen_codes:
            raise SetupError("fixture aliases and national codes must be unique")
        if session_id is not None and session_id in seen_sessions:
            raise SetupError("fixture session IDs must be unique")
        seen_aliases.add(alias)
        seen_codes.add(code)
        if session_id is not None:
            seen_sessions.add(session_id)
        identities.append(
            Identity(alias=alias, national_code=code, session_id=session_id)
        )

    custom = parse_scenarios(data.get("scenarios", {}), source="input fixture")
    return identities, custom


def parse_scenarios(
    raw_scenarios: Any,
    *,
    source: str,
) -> dict[str, tuple[ScenarioStep, ...]]:
    if not isinstance(raw_scenarios, dict):
        raise SetupError(f"{source} scenarios must be an object")
    custom: dict[str, tuple[ScenarioStep, ...]] = {}
    for scenario_name, raw_steps in raw_scenarios.items():
        if not isinstance(scenario_name, str) or not isinstance(raw_steps, list) or not raw_steps:
            raise SetupError(f"each {source} scenario must be a non-empty array")
        steps: list[ScenarioStep] = []
        for raw_step in raw_steps:
            if not isinstance(raw_step, dict):
                raise SetupError(f"scenario {scenario_name} contains a non-object step")
            query = raw_step.get("query")
            documents = raw_step.get("documents", ["General_FAQ"])
            step_name = raw_step.get("name", scenario_name)
            if (
                not isinstance(query, str)
                or not query.strip()
                or not isinstance(step_name, str)
                or not isinstance(documents, list)
                or not documents
                or not all(isinstance(item, str) and item for item in documents)
            ):
                raise SetupError(f"scenario {scenario_name} contains an invalid step")
            steps.append(ScenarioStep(step_name, query, tuple(documents)))
        custom[scenario_name] = tuple(steps)
    return custom


def load_scenario_file(path: Path) -> dict[str, tuple[ScenarioStep, ...]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupError(f"cannot read scenario file: {type(exc).__name__}") from exc
    if not isinstance(data, dict) or "scenarios" not in data:
        raise SetupError("scenario file must contain a scenarios object")
    return parse_scenarios(data["scenarios"], source="scenario file")


def validate_config(config: Config) -> None:
    calculate_total_requests(config.concurrency, config.repetitions)
    parsed = urlparse(config.base_url)
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise SetupError("base URL must contain a hostname")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    is_loopback = hostname == "localhost" or bool(
        address is not None and address.is_loopback
    )
    if address is not None and address.is_unspecified:
        raise SetupError(
            "0.0.0.0/:: are server bind addresses; use 127.0.0.1/::1 as the client host"
        )
    if parsed.scheme not in {"http", "https"}:
        raise SetupError("base URL scheme must be http or https")
    if parsed.scheme == "http" and not config.allow_http:
        raise SetupError("plain HTTP requires the explicit --allow-http option")
    staging_markers = ("staging", "stage", "stg", "test", "qa", "dev")
    if not is_loopback and not any(marker in hostname for marker in staging_markers):
        raise SetupError("base URL hostname must be explicitly staging/test/dev")
    if "prod" in hostname or "production" in hostname:
        raise SetupError("production-looking hosts are forbidden")
    if not config.verify_tls:
        raise SetupError("TLS verification cannot be disabled")
    if config.national_code_mode != "fixture":
        raise SetupError(
            "generated national codes are unsafe; use pre-created reserved staging fixtures"
        )
    if config.input_file is None:
        raise SetupError("--input-file is required for reserved staging identities")
    if not config.endpoint.startswith("/"):
        raise SetupError("endpoint must start with /")
    for name, value in {
        "request timeout": config.request_timeout,
        "connect timeout": config.connect_timeout,
        "write timeout": config.write_timeout,
        "pool timeout": config.pool_timeout,
    }.items():
        if value <= 0:
            raise SetupError(f"{name} must be positive")
    if config.request_timeout <= 50:
        raise SetupError("--request-timeout must exceed 50 seconds to observe the application deadline")
    if config.acquire_start_delay < 0:
        raise SetupError("--acquire-start-delay cannot be negative")
    if config.warmup_requests < 0:
        raise SetupError("--warmup-requests cannot be negative")
    if config.max_connections < config.concurrency:
        raise SetupError("--max-connections must be at least --concurrency")
    if not 0 < config.max_keepalive_connections <= config.max_connections:
        raise SetupError("keep-alive connections must be between 1 and max connections")
    if config.workload_mode == "arrival-rate":
        if config.arrival_rate is None or config.arrival_rate <= 0:
            raise SetupError("--arrival-rate must be positive in arrival-rate mode")
    elif config.arrival_rate is not None:
        raise SetupError("--arrival-rate is valid only in arrival-rate mode")
    if not 0 <= config.criteria.minimum_success_rate <= 1:
        raise SetupError("minimum success rate must be between 0 and 1")


def build_virtual_users(config: Config, identities: Sequence[Identity]) -> list[VirtualUser]:
    if len(identities) < config.concurrency:
        raise SetupError(
            f"fixture has {len(identities)} identities; {config.concurrency} are required"
        )
    rng = random.Random(config.seed)
    selected = list(identities)
    rng.shuffle(selected)
    return [
        VirtualUser(
            number=index,
            identity=selected[index - 1],
            session_id=(
                selected[index - 1].session_id
                or deterministic_session_id(
                    config.seed, config.session_prefix, index
                )
            ),
        )
        for index in range(1, config.concurrency + 1)
    ]


def sanitize_message(message: str, sensitive_values: Iterable[str] = ()) -> str:
    sanitized = message.replace("\r", " ").replace("\n", " ")
    for value in sensitive_values:
        if value:
            sanitized = sanitized.replace(value, "[redacted]")
    for marker in ("Bearer ", "Authorization:", "token="):
        if marker.lower() in sanitized.lower():
            return "sensitive error details redacted"
    return sanitized


def _safe_float(headers: httpx.Headers, *names: str) -> float | None:
    for name in names:
        value = headers.get(name)
        if value is None:
            continue
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) and parsed >= 0 else None
    return None


def _server_timing_values(headers: httpx.Headers) -> dict[str, str | float]:
    """Capture server timing headers without guessing unavailable stages."""

    values: dict[str, str | float] = {}
    for name, value in headers.multi_items():
        normalized = name.lower()
        if normalized == "server-timing" or (
            normalized.startswith("x-")
            and any(
                marker in normalized
                for marker in (
                    "timing",
                    "duration",
                    "processing",
                    "process-time",
                    "response-time",
                    "elapsed",
                    "wait",
                )
            )
        ):
            try:
                numeric = float(value)
            except ValueError:
                values[normalized] = value
            else:
                values[normalized] = (
                    numeric if math.isfinite(numeric) else value
                )
    return values


def _error_code(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(body, dict):
        return None
    value = body.get("errorCode")
    return value if isinstance(value, str) else None


def _server_request_id(response: httpx.Response) -> str | None:
    for header_name in ("x-request-id", "x-correlation-id", "request-id"):
        header_value = response.headers.get(header_name)
        if header_value:
            return sanitize_message(header_value)
    try:
        body = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(body, dict) or not isinstance(body.get("errorDetails"), dict):
        return None
    value = body["errorDetails"].get("requestId")
    return sanitize_message(value) if isinstance(value, str) and value else None


def classify_response(response: httpx.Response) -> tuple[str, str | None]:
    code = _error_code(response)
    if response.status_code == 503 and code == "SERVICE_BUSY":
        return LIMITER_REJECTION, "limiter"
    if response.status_code == 504 and code == "DEPENDENCY_TIMEOUT":
        return APPLICATION_DEADLINE, "application"
    if 400 <= response.status_code < 500:
        return HTTP_4XX, None
    if response.status_code >= 500:
        return HTTP_5XX, None
    if response.status_code == 200:
        return SUCCESS, None
    return UNEXPECTED_HTTP_STATUS, None


def classify_exception(exc: BaseException) -> tuple[str, str | None]:
    if isinstance(exc, httpx.PoolTimeout):
        return POOL_TIMEOUT, "pool"
    if isinstance(exc, httpx.ReadTimeout):
        return CLIENT_READ_TIMEOUT, "read"
    if isinstance(exc, httpx.ConnectTimeout):
        return CLIENT_CONNECT_TIMEOUT, "connect"
    if isinstance(exc, httpx.WriteTimeout):
        return CLIENT_WRITE_TIMEOUT, "write"
    if isinstance(exc, httpx.ConnectError):
        cause: BaseException | None = exc
        while cause is not None:
            if isinstance(cause, socket.gaierror):
                return DNS_FAILURE, "dns"
            cause = cause.__cause__
        return CONNECTION_ERROR, "connect"
    if isinstance(exc, asyncio.CancelledError):
        return CANCELLATION, "cancelled"
    return UNEXPECTED, None


def extract_talk_response(body: Any) -> tuple[bool, str, str | None]:
    """Validate the repository's TalkResponse and extract its `answer` field."""

    if not isinstance(body, dict):
        return False, "", "response body must be a JSON object"
    required_types: dict[str, type[Any]] = {
        "query_id": str,
        "session_id": str,
        "query": str,
        "answer": str,
        "related_questions": list,
        "feedback_needed": bool,
    }
    for key, expected in required_types.items():
        if key not in body:
            return False, "", f"TalkResponse is missing field: {key}"
        if not isinstance(body[key], expected):
            return (
                False,
                "",
                f"TalkResponse field {key} must be {expected.__name__}",
            )
    related = body["related_questions"]
    if not all(
        isinstance(item, dict)
        and all(isinstance(key, str) and isinstance(value, str) for key, value in item.items())
        for item in related
    ):
        return (
            False,
            "",
            "TalkResponse related_questions must contain string mappings",
        )
    return True, body["answer"], None


def validate_success_schema(body: Any) -> tuple[bool, int]:
    """Backward-compatible schema check used by existing callers/tests."""

    valid, answer, _ = extract_talk_response(body)
    return valid, len(answer) if valid else 0


async def perform_request(
    client: httpx.AsyncClient,
    config: Config,
    run_id: str,
    virtual_user: VirtualUser,
    wave_number: int,
    request_number: int,
    step: ScenarioStep,
    *,
    intended_start_ns: int | None = None,
) -> RequestRecord:
    start_ns = time.perf_counter_ns()
    start_timestamp = utc_now()
    scheduler_lag = (
        max(0.0, (start_ns - intended_start_ns) / 1_000_000)
        if intended_start_ns is not None
        else None
    )
    request_id = f"{run_id}-w{wave_number}-u{virtual_user.number}-r{request_number}"
    headers = {"X-Request-Id": request_id}
    if config.auth_token:
        headers["Authorization"] = f"Bearer {config.auth_token}"
    payload = {
        "session_id": virtual_user.session_id,
        "query": step.query,
        "national_code": virtual_user.identity.national_code,
        "documents": list(step.documents),
    }

    status: int | None = None
    failure_class = UNEXPECTED
    timeout_category: str | None = None
    exception_type: str | None = None
    sanitized_error: str | None = None
    response_bytes = 0
    answer_characters = 0
    answer_text = ""
    answer_word_count = 0
    response_schema_valid = False
    response_headers = httpx.Headers()
    try:
        response = await client.post(config.endpoint, json=payload, headers=headers)
        status = response.status_code
        response_bytes = len(response.content)
        response_headers = response.headers
        failure_class, timeout_category = classify_response(response)
        if failure_class == SUCCESS:
            try:
                response_body = response.json()
            except (json.JSONDecodeError, UnicodeDecodeError):
                failure_class = INVALID_SCHEMA
                sanitized_error = "successful HTTP response was not valid JSON"
            else:
                valid, answer_text, schema_error = extract_talk_response(
                    response_body
                )
                response_schema_valid = valid
                if valid:
                    answer_characters = len(answer_text)
                    answer_word_count = len(answer_text.split())
                else:
                    failure_class = INVALID_SCHEMA
                    sanitized_error = schema_error
        else:
            code = _error_code(response)
            sanitized_error = (
                f"HTTP {status}" + (f" errorCode={code}" if code else "")
            )
    except Exception as exc:
        failure_class, timeout_category = classify_exception(exc)
        exception_type = type(exc).__name__
        sanitized_error = sanitize_message(
            str(exc) or exception_type,
            (config.auth_token or "",),
        )

    end_ns = time.perf_counter_ns()
    return RequestRecord(
        run_id=run_id,
        wave_number=wave_number,
        virtual_user_number=virtual_user.number,
        request_number=request_number,
        scenario=step.name,
        session_id=virtual_user.session_id,
        national_code=virtual_user.identity.national_code,
        national_code_hash=national_code_hash(
            virtual_user.identity.national_code, run_id
        ),
        query_text=step.query,
        request_start_timestamp=start_timestamp,
        request_end_timestamp=utc_now(),
        start_perf_counter_ns=start_ns,
        end_perf_counter_ns=end_ns,
        client_elapsed_ms=(end_ns - start_ns) / 1_000_000,
        intended_start_perf_counter_ns=intended_start_ns,
        scheduler_lag_ms=scheduler_lag,
        http_status=status,
        failure_class=failure_class,
        response_bytes=response_bytes,
        answer_characters=answer_characters,
        answer_text=answer_text,
        answer_word_count=answer_word_count,
        answer_is_empty=response_schema_valid and answer_text == "",
        response_schema_valid=response_schema_valid,
        server_request_id=(
            _server_request_id(response) if status is not None else None
        ),
        server_timing=response_headers.get("server-timing"),
        server_timing_values=_server_timing_values(response_headers),
        limiter_wait_ms=_safe_float(
            response_headers, "x-limiter-wait-ms", "x-admission-wait-ms"
        ),
        endpoint_processing_ms=_safe_float(
            response_headers, "x-endpoint-processing-ms", "x-processing-time-ms"
        ),
        rewrite_duration_ms=_safe_float(response_headers, "x-rewrite-duration-ms"),
        embedding_duration_ms=_safe_float(
            response_headers, "x-embedding-duration-ms"
        ),
        qdrant_duration_ms=_safe_float(response_headers, "x-qdrant-duration-ms"),
        reranker_duration_ms=_safe_float(
            response_headers, "x-reranker-duration-ms"
        ),
        vllm_duration_ms=_safe_float(response_headers, "x-vllm-duration-ms"),
        timeout_category=timeout_category,
        exception_type=exception_type,
        sanitized_error=sanitized_error,
    )


async def run_burst_wave(
    jobs: Sequence[Callable[[], Awaitable[RequestRecord]]],
    acquire_start_delay: float,
    *,
    ready_callback: Callable[[int], None] | None = None,
) -> list[RequestRecord]:
    """Prepare all jobs, then release them together with an asyncio.Event."""

    release = asyncio.Event()
    all_ready = asyncio.Event()
    ready_count = 0
    ready_lock = asyncio.Lock()

    async def gated(job: Callable[[], Awaitable[RequestRecord]]) -> RequestRecord:
        nonlocal ready_count
        async with ready_lock:
            ready_count += 1
            if ready_callback:
                ready_callback(ready_count)
            if ready_count == len(jobs):
                all_ready.set()
        await release.wait()
        return await job()

    if not jobs:
        return []
    tasks = [asyncio.create_task(gated(job)) for job in jobs]
    await all_ready.wait()
    if acquire_start_delay:
        await asyncio.sleep(acquire_start_delay)
    release.set()
    return list(await asyncio.gather(*tasks))


class JsonlSink:
    """Flush each completed measured record so interruption retains evidence."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = asyncio.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    async def append_many(self, records: Iterable[RequestRecord]) -> None:
        lines = "".join(
            json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
            for record in records
        )
        async with self._lock:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(lines)
                stream.flush()


def _scenario_step(
    scenarios: Mapping[str, tuple[ScenarioStep, ...]],
    scenario_name: str,
    request_number: int,
) -> ScenarioStep:
    steps = scenarios[scenario_name]
    return steps[(request_number - 1) % len(steps)]


async def execute_workload(
    client: httpx.AsyncClient,
    config: Config,
    run_id: str,
    users: Sequence[VirtualUser],
    scenarios: Mapping[str, tuple[ScenarioStep, ...]],
    sink: JsonlSink | None = None,
) -> list[RequestRecord]:
    records: list[RequestRecord] = []

    async def execute(
        user: VirtualUser,
        wave: int,
        request_number: int,
        intended_start_ns: int | None = None,
    ) -> RequestRecord:
        return await perform_request(
            client,
            config,
            run_id,
            user,
            wave,
            request_number,
            _scenario_step(scenarios, config.scenario, request_number),
            intended_start_ns=intended_start_ns,
        )

    if config.workload_mode == "burst":
        for repetition in range(1, config.repetitions + 1):
            jobs = [
                (
                    lambda user=user, repetition=repetition: execute(
                        user, repetition, repetition
                    )
                )
                for user in users
            ]
            wave_records = await run_burst_wave(jobs, config.acquire_start_delay)
            records.extend(wave_records)
            if sink:
                await sink.append_many(wave_records)
    elif config.workload_mode == "closed-loop":
        async def worker(user: VirtualUser) -> list[RequestRecord]:
            worker_records = []
            for repetition in range(1, config.repetitions + 1):
                worker_records.append(await execute(user, repetition, repetition))
            return worker_records

        worker_results = await asyncio.gather(*(worker(user) for user in users))
        for worker_records in worker_results:
            records.extend(worker_records)
            if sink:
                await sink.append_many(worker_records)
    else:
        assert config.arrival_rate is not None
        origin_ns = time.perf_counter_ns()
        user_locks = [asyncio.Lock() for _ in users]

        async def scheduled(index: int) -> RequestRecord:
            offset_seconds = index / config.arrival_rate
            intended_ns = origin_ns + int(offset_seconds * 1_000_000_000)
            delay = (intended_ns - time.perf_counter_ns()) / 1_000_000_000
            if delay > 0:
                await asyncio.sleep(delay)
            user_index = index % config.concurrency
            request_number = index // config.concurrency + 1
            async with user_locks[user_index]:
                return await execute(
                    users[user_index],
                    request_number,
                    request_number,
                    intended_ns,
                )

        tasks = [
            asyncio.create_task(scheduled(index))
            for index in range(config.total_requests)
        ]
        for completed in asyncio.as_completed(tasks):
            record = await completed
            records.append(record)
            if sink:
                await sink.append_many([record])

    records.sort(key=lambda item: (item.start_perf_counter_ns, item.virtual_user_number))
    return records


def latency_statistics(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "minimum_ms": None,
            "maximum_ms": None,
            "mean_ms": None,
            "median_ms": None,
            "standard_deviation_ms": None,
            "p50_ms": None,
            "p75_ms": None,
            "p90_ms": None,
            "p95_ms": None,
            "p99_ms": None,
        }
    return {
        "count": len(values),
        "minimum_ms": min(values),
        "maximum_ms": max(values),
        "mean_ms": statistics.fmean(values),
        "median_ms": statistics.median(values),
        "standard_deviation_ms": statistics.pstdev(values),
        "p50_ms": percentile(values, 50),
        "p75_ms": percentile(values, 75),
        "p90_ms": percentile(values, 90),
        "p95_ms": percentile(values, 95),
        "p99_ms": percentile(values, 99),
    }


def answer_quality_statistics(
    records: Sequence[RequestRecord],
) -> dict[str, float | int | None]:
    valid_answers = [
        record.answer_text for record in records if record.response_schema_valid
    ]
    lengths = [len(answer) for answer in valid_answers]
    answer_counts = Counter(valid_answers)
    duplicate_count = sum(count - 1 for count in answer_counts.values() if count > 1)
    empty_count = sum(answer == "" for answer in valid_answers)
    identical_count = sum(
        record.response_schema_valid and record.answer_text == record.query_text
        for record in records
    )
    denominator = len(valid_answers)
    return {
        "answer_count": denominator,
        "empty_answer_count": empty_count,
        "empty_answer_percentage": (
            100 * empty_count / denominator if denominator else 0.0
        ),
        "minimum_answer_length": min(lengths) if lengths else None,
        "maximum_answer_length": max(lengths) if lengths else None,
        "average_answer_length": statistics.fmean(lengths) if lengths else None,
        "median_answer_length": statistics.median(lengths) if lengths else None,
        "duplicate_answer_count": duplicate_count,
        "duplicate_answer_percentage": (
            100 * duplicate_count / denominator if denominator else 0.0
        ),
        "answers_identical_to_query_count": identical_count,
        "invalid_response_schema_count": sum(
            record.failure_class == INVALID_SCHEMA for record in records
        ),
    }


def summarize_records(
    records: Sequence[RequestRecord],
    *,
    expected_attempts: int | None = None,
) -> dict[str, Any]:
    attempts = len(records)
    expected = attempts if expected_attempts is None else expected_attempts
    successful = [record for record in records if record.success]
    completed_latencies = [
        record.client_elapsed_ms
        for record in records
        if record.end_perf_counter_ns >= record.start_perf_counter_ns
    ]
    success_latencies = [record.client_elapsed_ms for record in successful]
    first_start = min((record.start_perf_counter_ns for record in records), default=0)
    last_end = max((record.end_perf_counter_ns for record in records), default=0)
    wall_seconds = max(0.0, (last_end - first_start) / 1_000_000_000)
    category_counts = Counter(record.failure_class for record in records)
    exception_counts = Counter(
        record.exception_type for record in records if record.exception_type
    )
    status_counts = Counter(
        str(record.http_status) if record.http_status is not None else "none"
        for record in records
    )
    success_count = len(successful)

    def percentage_within(seconds: float) -> float:
        if not success_latencies:
            return 0.0
        return 100 * sum(value <= seconds * 1000 for value in success_latencies) / len(
            success_latencies
        )

    return {
        "total_attempts": attempts,
        "expected_attempts": expected,
        "successful_responses": success_count,
        "failed_responses": attempts - success_count,
        "success_rate": success_count / attempts if attempts else 0.0,
        "completion_rate": attempts / expected if expected else 0.0,
        "excluded_from_success_percentiles": attempts - success_count,
        "excluded_failure_percentage": (
            100 * (attempts - success_count) / attempts if attempts else 0.0
        ),
        "limiter_rejections": category_counts[LIMITER_REJECTION],
        "application_deadline_timeouts": category_counts[APPLICATION_DEADLINE],
        "client_side_timeouts": sum(
            category_counts[key]
            for key in (
                CLIENT_READ_TIMEOUT,
                CLIENT_CONNECT_TIMEOUT,
                CLIENT_WRITE_TIMEOUT,
                POOL_TIMEOUT,
            )
        ),
        "http_4xx": sum(
            1
            for record in records
            if record.http_status is not None and 400 <= record.http_status < 500
        ),
        "http_5xx": sum(
            1
            for record in records
            if record.http_status is not None and record.http_status >= 500
        ),
        "connection_errors": sum(
            category_counts[key]
            for key in (DNS_FAILURE, CONNECTION_ERROR, CLIENT_CONNECT_TIMEOUT)
        ),
        "invalid_responses": category_counts[INVALID_SCHEMA],
        "cancellations": category_counts[CANCELLATION],
        "errors_by_exception_class": dict(sorted(exception_counts.items())),
        "counts_by_failure_category": dict(sorted(category_counts.items())),
        "counts_by_status_code": dict(sorted(status_counts.items())),
        "successful_latency_ms": latency_statistics(success_latencies),
        "all_completed_attempt_latency_ms": latency_statistics(completed_latencies),
        "requests_per_second": attempts / wall_seconds if wall_seconds else 0.0,
        "total_wall_clock_seconds": wall_seconds,
        "successful_within_10_seconds_percent": percentage_within(10),
        "successful_within_15_seconds_percent": percentage_within(15),
        "successful_within_20_seconds_percent": percentage_within(20),
        "successful_within_50_seconds_percent": percentage_within(50),
        "answer_quality": answer_quality_statistics(records),
    }


def grouped_statistics(records: Sequence[RequestRecord]) -> dict[str, Any]:
    dimensions: dict[str, Callable[[RequestRecord], str]] = {
        "by_wave": lambda record: str(record.wave_number),
        "by_scenario": lambda record: record.scenario,
        "by_status_code": lambda record: (
            str(record.http_status) if record.http_status is not None else "none"
        ),
        "by_failure_category": lambda record: record.failure_class,
    }
    result: dict[str, Any] = {}
    for dimension, key_function in dimensions.items():
        groups: dict[str, list[RequestRecord]] = {}
        for record in records:
            groups.setdefault(key_function(record), []).append(record)
        result[dimension] = {
            key: summarize_records(group) for key, group in sorted(groups.items())
        }
    return result


def evaluate_acceptance(
    summary: Mapping[str, Any],
    criteria: AcceptanceCriteria,
    *,
    per_wave: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    success_latency = summary["successful_latency_ms"]
    minimum_rate = 1.0 if criteria.strict else criteria.minimum_success_rate
    maximum_latency = (
        20_000.0 if criteria.strict else criteria.maximum_success_latency_ms
    )
    maximum_p95 = 20_000.0 if criteria.strict else criteria.maximum_p95_ms

    checks = [
        ("success_rate", summary["success_rate"], ">=", minimum_rate),
        ("p95_success_latency_ms", success_latency["p95_ms"], "<=", maximum_p95),
        (
            "maximum_success_latency_ms",
            success_latency["maximum_ms"],
            "<=",
            maximum_latency,
        ),
        (
            "application_deadline_timeouts",
            summary["application_deadline_timeouts"],
            "<=",
            criteria.maximum_application_deadline_timeouts,
        ),
        (
            "limiter_rejections",
            summary["limiter_rejections"],
            "<=",
            0 if criteria.strict else criteria.maximum_limiter_rejections,
        ),
        ("http_5xx", summary["http_5xx"], "<=", criteria.maximum_http_5xx),
    ]
    if criteria.strict:
        checks.append(("client_side_timeouts", summary["client_side_timeouts"], "<=", 0))

    for name, actual, operator, threshold in checks:
        passed = (
            actual is not None
            and (actual >= threshold if operator == ">=" else actual <= threshold)
        )
        if not passed:
            failures.append(
                {
                    "criterion": name,
                    "actual": actual,
                    "operator": operator,
                    "threshold": threshold,
                }
            )

    for wave, wave_summary in (per_wave or {}).items():
        wave_latency = wave_summary["successful_latency_ms"]
        for name, actual, operator, threshold in (
            ("success_rate", wave_summary["success_rate"], ">=", minimum_rate),
            ("p95_success_latency_ms", wave_latency["p95_ms"], "<=", maximum_p95),
            (
                "maximum_success_latency_ms",
                wave_latency["maximum_ms"],
                "<=",
                maximum_latency,
            ),
        ):
            passed = (
                actual is not None
                and (actual >= threshold if operator == ">=" else actual <= threshold)
            )
            if not passed:
                failures.append(
                    {
                        "criterion": f"wave_{wave}.{name}",
                        "actual": actual,
                        "operator": operator,
                        "threshold": threshold,
                    }
                )
    return {"passed": not failures, "failures": failures}


def exit_code_for(*, setup_valid: bool, acceptance_passed: bool) -> int:
    if not setup_valid:
        return EXIT_SETUP_FAILURE
    return EXIT_PASS if acceptance_passed else EXIT_ACCEPTANCE_FAILURE


def write_jsonl(path: Path, records: Sequence[RequestRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True))
            stream.write("\n")


def write_csv(path: Path, records: Sequence[RequestRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELD_NAMES)
        writer.writeheader()
        for record in records:
            writer.writerow(record.to_csv_dict())


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def environment_metadata(config: Config, run_id: str, started_at: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "timestamp_utc": started_at,
        "git_commit_sha": _git_sha(),
        "hostname": platform.node(),
        "python_version": platform.python_version(),
        "base_url": config.base_url,
        "endpoint": config.endpoint,
        "effective_url": urljoin(config.base_url.rstrip("/") + "/", config.endpoint.lstrip("/")),
        "concurrency": config.concurrency,
        "repetitions": config.repetitions,
        "total_requests": config.total_requests,
        "workload_mode": config.workload_mode,
        "arrival_rate_requests_per_second": config.arrival_rate,
        "scenario": config.scenario,
        "seed": config.seed,
        "warmup_requests": config.warmup_requests,
        "timeouts_seconds": {
            "connect": config.connect_timeout,
            "read": config.request_timeout,
            "write": config.write_timeout,
            "pool": config.pool_timeout,
        },
        "connection_limits": {
            "maximum_connections": config.max_connections,
            "maximum_keepalive_connections": config.max_keepalive_connections,
        },
        "tls_verification": config.verify_tls,
        "plain_http_exception_enabled": config.allow_http,
        "authentication": "configured" if config.auth_token else "not configured",
        "identity_source": "operator-provided reserved staging fixture",
        "input_file": "provided (path and contents omitted)",
        "scenario_file": (
            "provided (path and contents omitted)"
            if config.scenario_file
            else "not provided"
        ),
        "cleanup_manifest_requested": config.cleanup,
        "limiter_capacity": os.getenv(
            "RAGBOT_STAGING_LIMITER_CAPACITY", SOURCE_LIMITER_CAPACITY
        ),
        "staging_gpu_information": os.getenv(
            "RAGBOT_STAGING_GPU_INFO", SOURCE_STAGING_GPU
        ),
        "vllm_docker_image": os.getenv("RAGBOT_VLLM_IMAGE", "unknown"),
        "tei_embedding_docker_image": os.getenv(
            "RAGBOT_TEI_EMBED_IMAGE", "unknown"
        ),
        "tei_reranking_docker_image": os.getenv(
            "RAGBOT_TEI_RERANK_IMAGE", "unknown"
        ),
    }


def metric_explanations_markdown() -> str:
    return """## Metric explanations

- **Total attempts:** Total number of requests sent by the load generator.
- **Successful requests:** Requests that returned the expected HTTP status and a valid `TalkResponse`.
- **Success rate:** Successful requests divided by total attempts.
- **Minimum latency:** The fastest successful request in the measured run.
- **Maximum latency:** The slowest successful request.
- **Average latency:** Sum of successful-request latencies divided by the number of successful requests. Averages can hide slow tail requests.
- **Median or p50:** Half of successful requests completed faster and half completed slower.
- **p75:** 75% of successful requests completed within this duration.
- **p90:** 90% of successful requests completed within this duration.
- **p95:** 95% of successful requests completed within this duration. p95 is usually more useful than the average for understanding user-facing performance.
- **p99:** 99% of successful requests completed within this duration. p99 reveals tail latency, queueing, and occasional slow requests.
- **Standard deviation:** Measures how spread out request times are. A low value means consistent latency; a high value means unstable latency.
- **Throughput:** Number of completed requests divided by total wall-clock test duration. Throughput is not the same as concurrency.
- **Concurrency:** Number of requests intended to be active simultaneously.
- **Repetitions:** Number of repeated workload waves.
- **Total wall-clock duration:** Time between releasing the first measured request and receiving the last measured response.
- **Excluded failures:** Failed requests excluded from successful-request latency percentiles. They must still appear in failure counts.
- **Limiter rejection:** A request that could not acquire an application limiter slot within the configured acquisition timeout.
- **Application deadline timeout:** A request that entered application processing but exceeded the endpoint's 50-second deadline.
- **Client timeout:** The load generator stopped waiting before receiving a response.
- **Percentage within 10, 15, 20, and 50 seconds:** Percentage of successful requests completing within each latency threshold.

### Worked example

`PASS: 30/30 successful (100.00%); p95=9298.75 ms; max=9306.84 ms; excluded_failures=0; throughput=3.221 req/s`

All 30 requests completed successfully. 95% completed in approximately 9.30 seconds or less, and the slowest request completed in approximately 9.31 seconds. No failed requests were excluded from latency calculations. The full burst completed at an effective rate of approximately 3.22 requests per second.

Concurrency 30 does not mean throughput 30 requests per second. One repetition is not enough to establish stability; multiple repeated waves are needed. Passing at concurrency 30 does not prove concurrency 50 will pass. Response quality should be reviewed using `interactions.md`."""


def interactions_markdown(records: Sequence[RequestRecord]) -> str:
    sections: list[str] = []
    for interaction_number, record in enumerate(records, start=1):
        sections.extend(
            [
                f"## Interaction {interaction_number}",
                "",
                f"- Scenario: {record.scenario}",
                f"- Session ID: {record.session_id}",
                f"- National code: {record.national_code}",
                f"- Virtual user: {record.virtual_user_number}",
                f"- Wave: {record.wave_number}",
                f"- Request latency: {record.client_elapsed_ms:.2f} ms",
                f"- HTTP status: {record.http_status if record.http_status is not None else 'n/a'}",
                f"- Success: {'true' if record.success else 'false'}",
                f"- Request ID: {record.server_request_id or 'n/a'}",
                "",
                "### Query",
                "",
                record.query_text,
                "",
                "### Bot answer",
                "",
                record.answer_text,
                "",
            ]
        )
    return "\n".join(sections)


def report_markdown(summary: Mapping[str, Any]) -> str:
    metadata = summary["configuration"]
    global_stats = summary["global"]
    latency = global_stats["successful_latency_ms"]
    acceptance = summary["acceptance"]
    lines = [
        "# Mobile talk staging load-test report",
        "",
        f"- Result: **{'PASS' if acceptance['passed'] else 'FAIL'}**",
        f"- Run ID: `{metadata['run_id']}`",
        f"- Timestamp (UTC): {metadata['timestamp_utc']}",
        f"- Git commit: `{metadata['git_commit_sha']}`",
        f"- Hostname: `{metadata['hostname']}`",
        f"- Python: `{metadata['python_version']}`",
        f"- Endpoint: `{metadata['effective_url']}`",
        f"- Workload: {metadata['workload_mode']}; concurrency "
        f"{metadata['concurrency']}; repetitions {metadata['repetitions']}; "
        f"{metadata['total_requests']} measured requests",
        f"- Arrival rate: {metadata['arrival_rate_requests_per_second']}",
        f"- Scenario: `{metadata['scenario']}`; seed `{metadata['seed']}`",
        f"- Timeouts: `{json.dumps(metadata['timeouts_seconds'], sort_keys=True)}`",
        f"- Connection limits: `{json.dumps(metadata['connection_limits'], sort_keys=True)}`",
        f"- Source/live limiter capacity: {metadata['limiter_capacity']}",
        f"- Staging GPU: {metadata['staging_gpu_information']}",
        f"- vLLM image: {metadata['vllm_docker_image']}",
        f"- TEI embedding image: {metadata['tei_embedding_docker_image']}",
        f"- TEI reranking image: {metadata['tei_reranking_docker_image']}",
        f"- Acceptance criteria: `{json.dumps(summary['criteria'], sort_keys=True)}`",
        "",
        "Synthetic query text, bot answers, session IDs, and national codes are recorded "
        "in full. Authentication values remain omitted.",
        "Successful-response latency percentiles use R-7 linear interpolation.",
        f"They exclude {global_stats['excluded_from_success_percentiles']} failures "
        f"({global_stats['excluded_failure_percentage']:.2f}%).",
        "",
        "## Global metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Total attempts | {global_stats['total_attempts']} |",
        f"| Successful responses | {global_stats['successful_responses']} |",
        f"| Success rate | {global_stats['success_rate']:.2%} |",
        f"| Completion rate | {global_stats['completion_rate']:.2%} |",
        f"| Throughput | {global_stats['requests_per_second']:.3f} req/s |",
        f"| Wall-clock duration | {global_stats['total_wall_clock_seconds']:.3f} s |",
        f"| Successful p50 | {_format_ms(latency['p50_ms'])} |",
        f"| Successful p75 | {_format_ms(latency['p75_ms'])} |",
        f"| Successful p90 | {_format_ms(latency['p90_ms'])} |",
        f"| Successful p95 | {_format_ms(latency['p95_ms'])} |",
        f"| Successful p99 | {_format_ms(latency['p99_ms'])} |",
        f"| Minimum successful latency | {_format_ms(latency['minimum_ms'])} |",
        f"| Mean successful latency | {_format_ms(latency['mean_ms'])} |",
        f"| Median successful latency | {_format_ms(latency['median_ms'])} |",
        f"| Successful latency population stddev | {_format_ms(latency['standard_deviation_ms'])} |",
        f"| Maximum successful latency | {_format_ms(latency['maximum_ms'])} |",
        f"| Successful within 10 seconds | {global_stats['successful_within_10_seconds_percent']:.2f}% |",
        f"| Successful within 15 seconds | {global_stats['successful_within_15_seconds_percent']:.2f}% |",
        f"| Successful within 20 seconds | {global_stats['successful_within_20_seconds_percent']:.2f}% |",
        f"| Successful within 50 seconds | {global_stats['successful_within_50_seconds_percent']:.2f}% |",
        f"| Limiter rejections | {global_stats['limiter_rejections']} |",
        f"| Application deadline timeouts | {global_stats['application_deadline_timeouts']} |",
        f"| Client-side timeouts | {global_stats['client_side_timeouts']} |",
        f"| HTTP 4xx | {global_stats['http_4xx']} |",
        f"| HTTP 5xx | {global_stats['http_5xx']} |",
        f"| Connection errors | {global_stats['connection_errors']} |",
        f"| Invalid responses | {global_stats['invalid_responses']} |",
        f"| Cancellations | {global_stats['cancellations']} |",
        "",
        "## Answer-quality supporting metrics",
        "",
        "These are descriptive content checks only; semantic correctness is not "
        "scored automatically.",
        "Lengths are Unicode character counts for schema-valid answers. Duplicate "
        "count means repeated exact answer occurrences beyond the first, and "
        "percentages use the number of schema-valid answers as their denominator.",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Empty answers | {global_stats['answer_quality']['empty_answer_count']} |",
        f"| Empty-answer percentage | {global_stats['answer_quality']['empty_answer_percentage']:.2f}% |",
        f"| Minimum answer length | {global_stats['answer_quality']['minimum_answer_length']} |",
        f"| Maximum answer length | {global_stats['answer_quality']['maximum_answer_length']} |",
        f"| Average answer length | {_format_number(global_stats['answer_quality']['average_answer_length'])} |",
        f"| Median answer length | {_format_number(global_stats['answer_quality']['median_answer_length'])} |",
        f"| Duplicate answers | {global_stats['answer_quality']['duplicate_answer_count']} |",
        f"| Duplicate-answer percentage | {global_stats['answer_quality']['duplicate_answer_percentage']:.2f}% |",
        f"| Answers identical to query | {global_stats['answer_quality']['answers_identical_to_query_count']} |",
        f"| Invalid response schemas | {global_stats['answer_quality']['invalid_response_schema_count']} |",
        "",
        "## Metrics by wave",
        "",
        "| Wave | Attempts | Success rate | p95 success | Failures excluded |",
        "|---:|---:|---:|---:|---:|",
    ]
    for wave, stats in summary["groups"]["by_wave"].items():
        lines.append(
            f"| {wave} | {stats['total_attempts']} | {stats['success_rate']:.2%} | "
            f"{_format_ms(stats['successful_latency_ms']['p95_ms'])} | "
            f"{stats['excluded_from_success_percentiles']} |"
        )
    for title, key in (
        ("scenario", "by_scenario"),
        ("status code", "by_status_code"),
        ("failure category", "by_failure_category"),
    ):
        lines.extend(
            [
                "",
                f"## Metrics by {title}",
                "",
                "| Group | Attempts | Successes | p95 success | Excluded failures |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for group, stats in summary["groups"][key].items():
            lines.append(
                f"| {group} | {stats['total_attempts']} | "
                f"{stats['successful_responses']} | "
                f"{_format_ms(stats['successful_latency_ms']['p95_ms'])} | "
                f"{stats['excluded_from_success_percentiles']} |"
            )
    lines.extend(
        [
            "",
            "## Answer-quality metrics by scenario",
            "",
            "| Scenario | Answers | Empty | Empty % | Min chars | Max chars | "
            "Average chars | Median chars | Duplicates | Duplicate % | "
            "Identical to query | Invalid schema |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for scenario, stats in summary["groups"]["by_scenario"].items():
        quality = stats["answer_quality"]
        lines.append(
            f"| {scenario} | {quality['answer_count']} | "
            f"{quality['empty_answer_count']} | "
            f"{quality['empty_answer_percentage']:.2f}% | "
            f"{quality['minimum_answer_length']} | "
            f"{quality['maximum_answer_length']} | "
            f"{_format_number(quality['average_answer_length'])} | "
            f"{_format_number(quality['median_answer_length'])} | "
            f"{quality['duplicate_answer_count']} | "
            f"{quality['duplicate_answer_percentage']:.2f}% | "
            f"{quality['answers_identical_to_query_count']} | "
            f"{quality['invalid_response_schema_count']} |"
        )
    lines.extend(["", "## Acceptance", ""])
    if acceptance["passed"]:
        lines.append("All configured acceptance criteria passed.")
    else:
        lines.append("| Failed criterion | Actual | Requirement |")
        lines.append("|---|---:|---:|")
        for failure in acceptance["failures"]:
            lines.append(
                f"| {failure['criterion']} | {failure['actual']} | "
                f"{failure['operator']} {failure['threshold']} |"
            )
    lines.extend(
        [
            "",
            metric_explanations_markdown(),
            "",
            "Cleanup remains an operator-authorized staging database action. "
            "The runner never deletes application data.",
            "",
        ]
    )
    return "\n".join(lines)


def _format_ms(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f} ms"


def _format_number(value: float | int | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def write_artifacts(
    output_dir: Path,
    records: Sequence[RequestRecord],
    summary: Mapping[str, Any],
    *,
    cleanup: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "requests.jsonl", records)
    write_csv(output_dir / "requests.csv", records)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(
        report_markdown(summary), encoding="utf-8"
    )
    (output_dir / "interactions.md").write_text(
        interactions_markdown(records), encoding="utf-8"
    )
    if cleanup:
        cleanup_manifest = {
            "run_id": summary["configuration"]["run_id"],
            "warning": (
                "Operator action required: reconcile and remove only this run's "
                "staging records using an approved database procedure."
            ),
            "session_ids": sorted({record.session_id for record in records}),
            "national_codes": sorted({record.national_code for record in records}),
            "national_code_hashes": sorted(
                {record.national_code_hash for record in records}
            ),
            "full_national_codes_included": True,
        }
        (output_dir / "cleanup-manifest.json").write_text(
            json.dumps(cleanup_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def terminal_summary(summary: Mapping[str, Any], output_dir: Path) -> str:
    stats = summary["global"]
    latency = stats["successful_latency_ms"]
    result = "PASS" if summary["acceptance"]["passed"] else "FAIL"
    lines = [
        f"{result}: {stats['successful_responses']}/{stats['total_attempts']} "
        f"successful ({stats['success_rate']:.2%}); "
        f"p95={_format_ms(latency['p95_ms'])}; "
        f"max={_format_ms(latency['maximum_ms'])}; "
        f"excluded_failures={stats['excluded_from_success_percentiles']}; "
        f"throughput={stats['requests_per_second']:.3f} req/s",
        f"Failures: {stats['failed_responses']}; empty_answers="
        f"{stats['answer_quality']['empty_answer_count']}; invalid_schemas="
        f"{stats['answer_quality']['invalid_response_schema_count']}",
        "Artifacts:",
        f"- {output_dir / 'requests.jsonl'}",
        f"- {output_dir / 'requests.csv'}",
        f"- {output_dir / 'summary.json'}",
        f"- {output_dir / 'report.md'}",
        f"- {output_dir / 'interactions.md'}",
    ]
    if summary["configuration"].get("cleanup_manifest_requested"):
        lines.append(f"- {output_dir / 'cleanup-manifest.json'}")
    lines.append(
        f"Failed acceptance criteria: {len(summary['acceptance']['failures'])}"
    )
    return "\n".join(lines)


async def _warm_up(
    client: httpx.AsyncClient,
    config: Config,
    run_id: str,
    users: Sequence[VirtualUser],
    scenarios: Mapping[str, tuple[ScenarioStep, ...]],
) -> list[RequestRecord]:
    records = []
    for index in range(config.warmup_requests):
        user = users[index % len(users)]
        warmup_user = VirtualUser(
            number=user.number,
            identity=user.identity,
            session_id=deterministic_session_id(
                config.seed, f"{config.session_prefix}-warmup", index + 1
            ),
        )
        records.append(
            await perform_request(
                client,
                config,
                f"{run_id}-warmup",
                warmup_user,
                0,
                index + 1,
                _scenario_step(scenarios, config.scenario, index + 1),
            )
        )
    return records


async def run(config: Config) -> tuple[int, Path, dict[str, Any]]:
    validate_config(config)
    assert config.input_file is not None
    identities, custom_scenarios = load_fixture(config.input_file)
    if config.scenario_file is not None:
        custom_scenarios.update(load_scenario_file(config.scenario_file))
    scenarios = {**BUILTIN_SCENARIOS, **custom_scenarios}
    if config.scenario not in scenarios:
        raise SetupError(f"unknown scenario: {config.scenario}")
    users = build_virtual_users(config, identities)
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    timestamp_dir = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = config.output_dir or Path(
        "benchmarks/results/mobile-talk"
    ) / timestamp_dir
    if output_dir.exists() and any(output_dir.iterdir()):
        raise SetupError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    sink = JsonlSink(output_dir / "requests.jsonl")

    timeout = httpx.Timeout(
        connect=config.connect_timeout,
        read=config.request_timeout,
        write=config.write_timeout,
        pool=config.pool_timeout,
    )
    limits = httpx.Limits(
        max_connections=config.max_connections,
        max_keepalive_connections=config.max_keepalive_connections,
    )
    started_at = utc_now()
    async with httpx.AsyncClient(
        base_url=config.base_url,
        timeout=timeout,
        limits=limits,
        verify=config.verify_tls,
        follow_redirects=False,
    ) as client:
        warmups = await _warm_up(client, config, run_id, users, scenarios)
        if any(not record.success for record in warmups):
            warmup_summary = summarize_records(
                warmups, expected_attempts=config.warmup_requests
            )
            (output_dir / "warmup-summary.json").write_text(
                json.dumps(warmup_summary, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            raise SetupError(
                "warm-up failed; measured traffic was aborted. Inspect "
                f"{output_dir}/warmup-summary.json and perform run-scoped cleanup"
            )
        records = await execute_workload(
            client, config, run_id, users, scenarios, sink
        )

    global_summary = summarize_records(
        records, expected_attempts=config.total_requests
    )
    groups = grouped_statistics(records)
    acceptance = evaluate_acceptance(
        global_summary, config.criteria, per_wave=groups["by_wave"]
    )
    summary = {
        "configuration": environment_metadata(config, run_id, started_at),
        "criteria": asdict(config.criteria),
        "percentile_method": "R-7 linear interpolation",
        "global": global_summary,
        "groups": groups,
        "warmup": summarize_records(
            warmups, expected_attempts=config.warmup_requests
        ),
        "acceptance": acceptance,
    }
    write_artifacts(
        output_dir, records, summary, cleanup=config.cleanup
    )
    return (
        exit_code_for(setup_valid=True, acceptance_passed=acceptance["passed"]),
        output_dir,
        summary,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Staging-only async load test for the mobile talk endpoint"
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--request-timeout", type=float, default=55.0)
    parser.add_argument("--connect-timeout", type=float, default=5.0)
    parser.add_argument("--write-timeout", type=float, default=10.0)
    parser.add_argument("--pool-timeout", type=float, default=5.0)
    parser.add_argument("--acquire-start-delay", type=float, default=0.05)
    parser.add_argument("--scenario", default="faq")
    parser.add_argument("--input-file", type=Path)
    parser.add_argument("--scenario-file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--seed", type=int, default=20260728)
    parser.add_argument("--auth-token")
    parser.add_argument(
        "--verify-tls",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="TLS verification is mandatory; --no-verify-tls is rejected",
    )
    parser.add_argument(
        "--allow-http",
        action="store_true",
        help=(
            "explicitly allow plain HTTP for loopback or staging/test/dev hosts; "
            "production-looking and 0.0.0.0 targets remain forbidden"
        ),
    )
    parser.add_argument("--warmup-requests", type=int, default=0)
    parser.add_argument("--session-prefix", default="ragbot-load")
    parser.add_argument(
        "--national-code-mode",
        choices=("fixture", "iranian-checksum"),
        default="fixture",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="write a manual cleanup manifest; never performs database deletion",
    )
    parser.add_argument(
        "--workload-mode",
        choices=("burst", "closed-loop", "arrival-rate"),
        default="burst",
    )
    parser.add_argument("--arrival-rate", type=float)
    parser.add_argument("--max-connections", type=int, default=100)
    parser.add_argument("--max-keepalive-connections", type=int, default=50)
    parser.add_argument("--minimum-success-rate", type=float, default=0.99)
    parser.add_argument("--maximum-p95", type=float, default=20.0)
    parser.add_argument("--maximum-success-latency", type=float, default=20.0)
    parser.add_argument(
        "--maximum-application-deadline-timeouts", type=int, default=0
    )
    parser.add_argument("--maximum-limiter-rejections", type=int, default=0)
    parser.add_argument("--maximum-http-5xx", type=int, default=0)
    parser.add_argument("--strict", action="store_true")
    return parser


def config_from_args(args: argparse.Namespace) -> Config:
    token = args.auth_token or os.getenv("RAGBOT_STAGING_AUTH_TOKEN")
    return Config(
        base_url=args.base_url,
        endpoint=args.endpoint,
        concurrency=args.concurrency,
        repetitions=args.repetitions,
        request_timeout=args.request_timeout,
        connect_timeout=args.connect_timeout,
        write_timeout=args.write_timeout,
        pool_timeout=args.pool_timeout,
        acquire_start_delay=args.acquire_start_delay,
        scenario=args.scenario,
        input_file=args.input_file,
        scenario_file=args.scenario_file,
        output_dir=args.output_dir,
        seed=args.seed,
        auth_token=token,
        verify_tls=args.verify_tls,
        allow_http=args.allow_http,
        warmup_requests=args.warmup_requests,
        session_prefix=args.session_prefix,
        national_code_mode=args.national_code_mode,
        cleanup=args.cleanup,
        workload_mode=args.workload_mode,
        arrival_rate=args.arrival_rate,
        max_connections=args.max_connections,
        max_keepalive_connections=args.max_keepalive_connections,
        criteria=AcceptanceCriteria(
            minimum_success_rate=args.minimum_success_rate,
            maximum_p95_ms=args.maximum_p95 * 1000,
            maximum_success_latency_ms=args.maximum_success_latency * 1000,
            maximum_application_deadline_timeouts=(
                args.maximum_application_deadline_timeouts
            ),
            maximum_limiter_rejections=args.maximum_limiter_rejections,
            maximum_http_5xx=args.maximum_http_5xx,
            strict=args.strict,
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.auth_token:
        print(
            "WARNING: --auth-token may be visible in shell history/process lists; "
            "prefer RAGBOT_STAGING_AUTH_TOKEN.",
            file=sys.stderr,
        )
    try:
        code, output_dir, summary = asyncio.run(run(config_from_args(args)))
    except (SetupError, OSError) as exc:
        print(f"SETUP ERROR: {sanitize_message(str(exc))}", file=sys.stderr)
        return EXIT_SETUP_FAILURE
    except KeyboardInterrupt:
        print("SETUP ERROR: interrupted; inspect partial JSONL and perform cleanup", file=sys.stderr)
        return EXIT_SETUP_FAILURE
    print(terminal_summary(summary, output_dir))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
