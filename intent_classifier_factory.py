"""One validated env-backed construction path for the intent classifier."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass

from intent_classifier import IntentClassifier


@dataclass(frozen=True)
class IntentClassifierConfig:
    model_path: str
    threshold: float
    device: str
    required: bool
    expected_sha256: str | None


def _parse_bool(name: str, value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def load_intent_classifier_config(
    environ: Mapping[str, str] | None = None,
) -> IntentClassifierConfig:
    values = os.environ if environ is None else environ
    required = _parse_bool(
        "INTENT_CLASSIFIER_REQUIRED", values.get("INTENT_CLASSIFIER_REQUIRED")
    )
    model_path = (values.get("INTENT_CLASSIFIER_MODEL_PATH") or "").strip()
    device = (values.get("INTENT_CLASSIFIER_DEVICE") or "").strip()
    raw_threshold = (values.get("INTENT_CLASSIFIER_THRESHOLD") or "").strip()
    expected_sha256 = (
        values.get("INTENT_CLASSIFIER_EXPECTED_SHA256") or ""
    ).strip().lower() or None
    if not model_path:
        raise ValueError("INTENT_CLASSIFIER_MODEL_PATH must be configured")
    if not device:
        raise ValueError("INTENT_CLASSIFIER_DEVICE must be configured")
    try:
        threshold = float(raw_threshold)
    except ValueError as exc:
        raise ValueError("INTENT_CLASSIFIER_THRESHOLD must be numeric") from exc
    if not 0.0 < threshold < 1.0:
        raise ValueError("INTENT_CLASSIFIER_THRESHOLD must be between 0 and 1")
    if required and not expected_sha256:
        raise ValueError(
            "INTENT_CLASSIFIER_EXPECTED_SHA256 is required when classifier is required"
        )
    return IntentClassifierConfig(
        model_path=model_path,
        threshold=threshold,
        device=device,
        required=required,
        expected_sha256=expected_sha256,
    )


def build_intent_classifier(
    *,
    embedding_model: Callable[[str], Awaitable[Sequence[float]]],
    scenarios_path: str = "scenarios.json",
    blocking_runner=None,
    environ: Mapping[str, str] | None = None,
) -> IntentClassifier:
    config = load_intent_classifier_config(environ)
    return IntentClassifier(
        embedding_model=embedding_model,
        scenarios_path=scenarios_path,
        classifier_model_path=config.model_path,
        similarity_threshold=config.threshold,
        device=config.device,
        required=config.required,
        expected_sha256=config.expected_sha256,
        blocking_runner=blocking_runner,
    )
