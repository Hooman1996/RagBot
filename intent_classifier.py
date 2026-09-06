"""Deterministic binary intent guardrail using retrieval-query embeddings."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import threading
import time
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn

from pipeline_observer import PipelineStage, PipelineStageResult, emit_pipeline_stage_lazy
from utils.persian_normalization import normalize_persian_text


JINA_DIM = 1024
LABEL_ACTIONABLE = 0
LABEL_CHITCHAT = 1
EXPECTED_LABEL_MAP = {"0": "ACTIONABLE_INTENT", "1": "CHITCHAT"}
EXPECTED_ARCHITECTURE = "1024-512-128-32-2"
EXPECTED_EMBEDDING_ROLE = "retrieval_query"
EXPECTED_EMBEDDING_PROMPT = "query"


class _GuardrailNet(nn.Module):
    """Fixed 1024 -> 512 -> 128 -> 32 -> 2 CrossEntropy MLP."""

    def __init__(self, dropout_shallow: float = 0.2, dropout_deep: float = 0.4):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(JINA_DIM, 512),
            nn.BatchNorm1d(512),
            nn.GELU(),
            nn.Dropout(dropout_shallow),
            nn.Linear(512, 128),
            nn.BatchNorm1d(128),
            nn.GELU(),
            nn.Dropout(dropout_deep),
            nn.Linear(128, 32),
            nn.BatchNorm1d(32),
            nn.GELU(),
            nn.Dropout(dropout_deep),
            nn.Linear(32, 2),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.net(features)


class IntentClassifier:
    """Route label 0 to RAG and label 1 to the chitchat handler."""

    def __init__(
        self,
        embedding_model: Callable[[str], Awaitable[Sequence[float]]] | None = None,
        scenarios_path: str = "scenarios.json",
        *,
        classifier_model_path: str | None,
        similarity_threshold: float,
        device: str,
        required: bool,
        expected_sha256: str | None,
        blocking_runner=None,
    ) -> None:
        if not callable(embedding_model):
            raise TypeError("embedding_model must be an async embedding callable")
        if not 0.0 < similarity_threshold < 1.0:
            raise ValueError("similarity_threshold must be between 0 and 1")
        if not isinstance(device, str) or not device.strip():
            raise ValueError("device must be an explicit non-empty string")

        self.embedding_model = embedding_model
        self.blocking_runner = blocking_runner
        self._inference_lock = threading.Lock()
        self.threshold = float(similarity_threshold)
        self.required = bool(required)
        self.device = torch.device(device)
        self.model_path = str(classifier_model_path) if classifier_model_path else None
        self.model_path_basename = Path(self.model_path).name if self.model_path else None
        self.checkpoint_sha256: str | None = None
        self.embedding_dimension = JINA_DIM
        self.embedding_role = EXPECTED_EMBEDDING_ROLE
        self.embedding_prompt_name = EXPECTED_EMBEDDING_PROMPT
        self.scenarios = self._load_scenarios(scenarios_path)
        self.scenario_embeddings: dict[str, np.ndarray] = {}
        self._checkpoint_loaded = False
        self.classifier = _GuardrailNet()

        normalized_sha = expected_sha256.strip().lower() if expected_sha256 else None
        if normalized_sha and not re.fullmatch(r"[0-9a-f]{64}", normalized_sha):
            raise ValueError("expected_sha256 must be a 64-character SHA256")
        if self.required and not normalized_sha:
            raise ValueError("expected_sha256 is required when classifier is required")

        if self.model_path and os.path.isfile(self.model_path):
            self.checkpoint_sha256 = self._sha256_file(Path(self.model_path))
            if normalized_sha and self.checkpoint_sha256 != normalized_sha:
                raise ValueError("Intent classifier checkpoint SHA256 mismatch")
            checkpoint = torch.load(
                self.model_path, map_location=self.device, weights_only=True
            )
            if not isinstance(checkpoint, dict) or "model_state_dict" not in checkpoint:
                raise ValueError("Intent classifier checkpoint lacks model_state_dict")
            self._validate_checkpoint_metadata(checkpoint)
            self.classifier.load_state_dict(checkpoint["model_state_dict"], strict=True)
            self._checkpoint_loaded = True
        elif self.required:
            raise FileNotFoundError(
                f"Required intent classifier checkpoint not found: {self.model_path}"
            )

        self.classifier.to(self.device)
        self.classifier.eval()

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _validate_checkpoint_metadata(self, checkpoint: dict[str, Any]) -> None:
        checks = {
            "architecture": EXPECTED_ARCHITECTURE,
            "embedding_dimension": JINA_DIM,
            "embedding_role": EXPECTED_EMBEDDING_ROLE,
            "embedding_prompt_name": EXPECTED_EMBEDDING_PROMPT,
            "embedding_normalize": True,
            "normalizer": "normalize_persian_text",
        }
        for key, expected in checks.items():
            if checkpoint.get(key) != expected:
                raise ValueError(
                    f"Intent classifier checkpoint {key} must be {expected!r}"
                )
        label_map = {
            str(key): value for key, value in checkpoint.get("label_map", {}).items()
        }
        if label_map != EXPECTED_LABEL_MAP:
            raise ValueError("Intent classifier checkpoint label_map is incompatible")
        selected_threshold = checkpoint.get("selected_threshold")
        if not isinstance(selected_threshold, (int, float)) or not np.isclose(
            float(selected_threshold), self.threshold, rtol=0.0, atol=1e-12
        ):
            raise ValueError(
                "Configured intent threshold does not match checkpoint metadata"
            )

    @staticmethod
    def _load_scenarios(path: str) -> list[dict[str, Any]]:
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream).get("scenarios", [])

    async def _encode(self, query: str) -> np.ndarray:
        embedding = np.asarray(await self.embedding_model(query), dtype=np.float32)
        if embedding.shape != (JINA_DIM,):
            raise ValueError(
                f"Classifier embedding must have {JINA_DIM} dimensions; "
                f"received shape {embedding.shape}"
            )
        return embedding

    async def classify(self, query: str) -> dict[str, str | None]:
        detailed = await self._classify_detailed(query)
        return {"type": detailed["type"], "scenario_id": detailed["scenario_id"]}

    async def classify_detailed(self, query: str) -> dict[str, Any]:
        return await self._classify_detailed(query)

    async def _classify_detailed(self, query: str) -> dict[str, Any]:
        started = time.perf_counter()
        preprocessed_query = normalize_persian_text(query) if query else ""
        if not preprocessed_query:
            result = self._actionable_result(preprocessed_query)
            self._emit_trace(started, query, result)
            return result

        embedding = await self._encode(preprocessed_query)
        if self.blocking_runner is not None:
            values = await self.blocking_runner.run(self._classify_embedding, embedding)
        else:
            values = await asyncio.to_thread(self._classify_embedding, embedding)
        class_id, confidence, p_actionable, p_chitchat = values
        is_chitchat = class_id == LABEL_CHITCHAT
        result = {
            "type": "chitchat" if is_chitchat else "general",
            "scenario_id": "chitchat" if is_chitchat else None,
            "class_id": class_id,
            "selected_class": EXPECTED_LABEL_MAP[str(class_id)],
            "confidence": confidence,
            "p_actionable": p_actionable,
            "p_chitchat": p_chitchat,
            "route_to_rag": not is_chitchat,
            "preprocessed_query": preprocessed_query,
            "effective_threshold": self.threshold,
        }
        self._emit_trace(started, query, result)
        return result

    def _actionable_result(self, preprocessed_query: str) -> dict[str, Any]:
        return {
            "type": "general",
            "scenario_id": None,
            "class_id": LABEL_ACTIONABLE,
            "selected_class": EXPECTED_LABEL_MAP[str(LABEL_ACTIONABLE)],
            "confidence": 1.0,
            "p_actionable": 1.0,
            "p_chitchat": 0.0,
            "route_to_rag": True,
            "preprocessed_query": preprocessed_query,
            "effective_threshold": self.threshold,
        }

    def _emit_trace(
        self, started: float, raw_query: str | None, result: dict[str, Any]
    ) -> None:
        emit_pipeline_stage_lazy(
            lambda: PipelineStageResult(
                stage=PipelineStage.INTENT,
                input_data={"classifier_input": raw_query},
                output_data=result,
                metrics={
                    "effective_threshold": self.threshold,
                    "embedding_dimension": JINA_DIM,
                    "embedding_role": EXPECTED_EMBEDDING_ROLE,
                    "embedding_prompt_name": EXPECTED_EMBEDDING_PROMPT,
                },
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        )

    def _classify_embedding(
        self, embedding: np.ndarray
    ) -> tuple[int, float, float, float]:
        """Run a locked, eval-mode, no-grad Torch forward pass."""
        if not self._checkpoint_loaded:
            return LABEL_ACTIONABLE, 1.0, 1.0, 0.0
        with self._inference_lock:
            features = torch.as_tensor(
                embedding, dtype=torch.float32, device=self.device
            ).unsqueeze(0)
            with torch.no_grad():
                probabilities = torch.softmax(
                    self.classifier(features), dim=1
                ).squeeze(0)
            p_actionable = float(probabilities[LABEL_ACTIONABLE].item())
            p_chitchat = float(probabilities[LABEL_CHITCHAT].item())
            class_id = (
                LABEL_CHITCHAT if p_chitchat >= self.threshold else LABEL_ACTIONABLE
            )
            return (
                class_id,
                p_chitchat if class_id == LABEL_CHITCHAT else p_actionable,
                p_actionable,
                p_chitchat,
            )
