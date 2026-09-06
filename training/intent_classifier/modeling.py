"""Checkpoint compatibility and evaluation helpers for the fixed MLP."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import torch

from intent_classifier import JINA_DIM, LABEL_ACTIONABLE, LABEL_CHITCHAT, _GuardrailNet
from training.intent_classifier.common import LABEL_MAP, classification_metrics, subgroup_metrics


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_compatible_checkpoint(path: Path, device: torch.device) -> tuple[_GuardrailNet, dict[str, Any]]:
    payload = torch.load(path, map_location=device, weights_only=True)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a checkpoint dictionary")
    if "model_state_dict" in payload:
        state = payload["model_state_dict"]
    elif "model_state" in payload:
        state = payload["model_state"]
    else:
        state = payload
    model = _GuardrailNet()
    incompatible = model.load_state_dict(state, strict=True)
    if incompatible.missing_keys or incompatible.unexpected_keys:
        raise ValueError(f"Checkpoint mismatch: {incompatible}")
    if int(payload.get("input_dim", JINA_DIM)) != JINA_DIM:
        raise ValueError(f"Checkpoint input_dim is not {JINA_DIM}")
    label_map = payload.get("label_map", LABEL_MAP)
    normalized_map = {int(key): value for key, value in label_map.items()}
    if normalized_map != LABEL_MAP:
        raise ValueError(f"Checkpoint label map changed: {normalized_map}")
    model.to(device)
    return model, payload


def predict_probabilities(model: torch.nn.Module, embeddings: np.ndarray, device: torch.device, batch_size: int = 1024) -> np.ndarray:
    model.eval()
    results: list[np.ndarray] = []
    with torch.no_grad():
        for offset in range(0, len(embeddings), batch_size):
            features = torch.from_numpy(embeddings[offset : offset + batch_size]).to(device)
            probabilities = torch.softmax(model(features), dim=1)
            results.append(probabilities.cpu().numpy())
    output = np.concatenate(results, axis=0)
    if output.shape != (len(embeddings), 2):
        raise ValueError(f"Unexpected prediction shape: {output.shape}")
    return output


def evaluate_rows(rows: Sequence[dict[str, Any]], probabilities: np.ndarray, threshold: float = 0.5) -> dict[str, Any]:
    labels = [int(row["label"]) for row in rows]
    predictions = (probabilities[:, LABEL_CHITCHAT] >= threshold).astype(np.int64)
    metrics = classification_metrics(labels, predictions)
    metrics["threshold_p_chitchat"] = threshold
    metrics["subgroups"] = subgroup_metrics(rows, predictions)
    metrics["label_order"] = {"0": "banking/in-scope", "1": "chit-chat/non-banking/out-of-scope"}
    metrics["banking_recall"] = metrics["per_class"]["banking"]["recall"]
    metrics["chitchat_recall"] = metrics["per_class"]["chitchat_nonbanking"]["recall"]
    return metrics


def compatible_payload(initial_payload: dict[str, Any], model: torch.nn.Module, *, jina_task: str | None = None) -> dict[str, Any]:
    """Preserve the exact loader-facing keys and attach no executable objects."""
    return {
        "model_state_dict": model.state_dict(),
        "input_dim": JINA_DIM,
        "jina_model": initial_payload.get("jina_model", "unknown"),
        "jina_task": jina_task or initial_payload.get("jina_task", "classification"),
        "label_map": {LABEL_ACTIONABLE: "ACTIONABLE_INTENT", LABEL_CHITCHAT: "CHIT-CHAT"},
    }
