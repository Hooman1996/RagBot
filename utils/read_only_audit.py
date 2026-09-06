"""Deterministic, content-safe primitives for read-only audit reports."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import struct
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


def json_safe(value: Any) -> Any:
    """Convert SDK/model values into deterministic JSON-compatible values."""

    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("audit values must contain only finite floats")
        return value
    if isinstance(value, Enum):
        return json_safe(value.value)
    if dataclasses.is_dataclass(value):
        return json_safe(dataclasses.asdict(value))
    if hasattr(value, "model_dump"):
        return json_safe(value.model_dump(mode="json", exclude_none=True))
    if hasattr(value, "dict"):
        return json_safe(value.dict(exclude_none=True))
    if isinstance(value, dict):
        return {
            str(key): json_safe(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted((json_safe(item) for item in value), key=repr)
    return str(value)


def canonical_json(value: Any) -> str:
    return json.dumps(
        json_safe(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def vector_float32_le_signature(values: Iterable[float]) -> dict[str, Any]:
    """Hash canonical IEEE-754 float32 little-endian bytes without retaining them."""

    digest = hashlib.sha256()
    dimension = 0
    for raw in values:
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError("vectors must contain only finite numeric values")
        digest.update(struct.pack("<f", value))
        dimension += 1
    return {
        "dimension": dimension,
        "sha256": digest.hexdigest(),
    }


def float64_le_hex(value: float) -> str:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError("scores must be finite")
    return struct.pack("<d", numeric).hex()


def write_json_report(path: Path, payload: Any) -> None:
    """Write a human-readable report atomically inside its destination directory."""

    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(
            json_safe(payload),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
