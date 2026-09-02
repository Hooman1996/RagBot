"""
intent_classifier.py
====================
Drop-in production replacement for the previous IntentClassifier.

What changed vs. the old version
─────────────────────────────────
  • Neural network: 1024→512→128→32→2  (CrossEntropy, 2 logits)
                    replaces 1024→128→1 (Sigmoid, 1 logit)
  • Checkpoint key: "model_state_dict"  (saved by chitchat_guardrail.py)
                    replaces "model_state"
  • Embedding task: task="classification"  (Jina v5 classification LoRA adapter)
                    replaces no task tag
  • Label mapping:  0 = ACTIONABLE_INTENT  |  1 = CHIT-CHAT
                    (stored inside the checkpoint under "label_map")

Public interface:
  await classifier.classify(query) → {"type": "general"|"chitchat", "scenario_id": str|None}
"""

import os
import asyncio
import threading
import json
from collections.abc import Awaitable, Callable
from typing import Dict, List, Optional, Sequence

import numpy as np
import torch
import torch.nn as nn

from utils.persian_normalization import normalize_persian_text
from pipeline_observer import (
    PipelineStage,
    PipelineStageResult,
    emit_pipeline_stage_lazy,
)
import time


# ─────────────────────────────────────────────────────────────────────────────
# Constants  (must match chitchat_guardrail.py exactly)
# ─────────────────────────────────────────────────────────────────────────────

JINA_DIM         = 1024
LABEL_ACTIONABLE = 0    # → route to RAG pipeline  → type="general"
LABEL_CHITCHAT   = 1    # → skip RAG pipeline       → type="chitchat"


# ─────────────────────────────────────────────────────────────────────────────
# Neural network architecture
# Must be identical to ChitChatGuardrail in chitchat_guardrail.py so that
# torch.load() + load_state_dict() succeed.
# ─────────────────────────────────────────────────────────────────────────────

class _GuardrailNet(nn.Module):
    """
    Internal MLP.  Do not instantiate directly — use IntentClassifier.

    Architecture : 1024 → 512 → 128 → 32 → 2
    Output logits: [:, 0] = ACTIONABLE_INTENT  |  [:, 1] = CHIT-CHAT
    """

    def __init__(self, dropout_shallow: float = 0.2, dropout_deep: float = 0.4):
        super().__init__()
        self.net = nn.Sequential(
            # Block 1: 1024 → 512
            nn.Linear(JINA_DIM, 512),
            nn.BatchNorm1d(512),
            nn.GELU(),
            nn.Dropout(dropout_shallow),

            # Block 2: 512 → 128
            nn.Linear(512, 128),
            nn.BatchNorm1d(128),
            nn.GELU(),
            nn.Dropout(dropout_deep),

            # Block 3: 128 → 32
            nn.Linear(128, 32),
            nn.BatchNorm1d(32),
            nn.GELU(),
            nn.Dropout(dropout_deep),

            # Output: 32 → 2 logits
            nn.Linear(32, 2),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


# ─────────────────────────────────────────────────────────────────────────────
# Public class
# ─────────────────────────────────────────────────────────────────────────────

class IntentClassifier:
    """
    Classifies a user query into:
        type        : "general"  → proceed to RAG pipeline
                    | "chitchat" → skip RAG, return polite deflection
        scenario_id : "chitchat" when type=="chitchat", else None

    Usage
    ─────
        from intent_classifier import IntentClassifier

        classifier = IntentClassifier(embedding_model=async_tei_embed)

        result = await classifier.classify("موجودی حسابم چنده؟")
        # → {"type": "general", "scenario_id": None}

        result = await classifier.classify("سلام، خوبی؟")
        # → {"type": "chitchat", "scenario_id": "chitchat"}
    """

    def __init__(
        self,
        embedding_model      : Optional[Callable[[str], Awaitable[Sequence[float]]]] = None,
        scenarios_path       : str            = "scenarios.json",
        similarity_threshold : float          = 0.875,
        classifier_model_path: Optional[str]  = "chitchat_guardrail_finetuned.pt",
        device               : Optional[str]  = None,             # None = auto-detect
        blocking_runner       = None,
    ):
        if not callable(embedding_model):
            raise TypeError("embedding_model must be an async embedding callable")
        self.embedding_model = embedding_model
        self.blocking_runner = blocking_runner
        self._inference_lock = threading.Lock()

        if not 0.0 < similarity_threshold < 1.0:
            raise ValueError("similarity_threshold must be between 0 and 1")
        # Route to chit-chat only when its softmax probability clears the
        # validation-selected boundary. Ambiguous predictions stay in the safer
        # banking/RAG route.
        self.threshold = similarity_threshold

        # Scenarios are still loaded so existing code that reads self.scenarios
        # keeps working, even though scenario-based routing is currently disabled.
        self.scenarios          = self._load_scenarios(scenarios_path)
        self.scenario_embeddings: Dict[str, np.ndarray] = {}

        # ── Device ────────────────────────────────────────────────────────────
        if device is not None:
            self.device = torch.device(device)
        else:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # ── Build classifier network ──────────────────────────────────────────
        self.classifier = _GuardrailNet()

        # ── Load checkpoint ───────────────────────────────────────────────────
        if classifier_model_path and os.path.exists(classifier_model_path):
            checkpoint = torch.load(
                classifier_model_path,
                map_location=self.device,
                weights_only=True,          # safe loading — no arbitrary code exec
            )

            # Checkpoint saved by chitchat_guardrail.py is always a dict with
            # "model_state_dict".  Guard against old-format checkpoints too.
            if isinstance(checkpoint, dict):
                if "model_state_dict" in checkpoint:
                    state_dict = checkpoint["model_state_dict"]
                elif "model_state" in checkpoint:
                    # legacy key from the previous classifier version
                    state_dict = checkpoint["model_state"]
                    print("⚠️  Loaded legacy checkpoint key 'model_state'. "
                          "Re-train with chitchat_guardrail.py for best results.")
                else:
                    state_dict = checkpoint
            else:
                state_dict = checkpoint

            self.classifier.load_state_dict(state_dict)
            print(f"✓ Classifier loaded from '{classifier_model_path}' onto {self.device}")
        else:
            print(f"⚠️  Classifier checkpoint not found at '{classifier_model_path}'. "
                  "Running without a trained model — all queries will be routed to RAG.")

        # Move to device and lock into eval mode
        self.classifier.to(self.device)
        self.classifier.eval()

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _load_scenarios(self, path: str) -> List[Dict]:
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("scenarios", [])

    async def _encode(self, query: str) -> np.ndarray:
        """
        Encode a single query through the configured TEI embedding callable.
        """
        embedding = np.asarray(await self.embedding_model(query), dtype=np.float32)
        if embedding.shape != (JINA_DIM,):
            raise ValueError(
                f"Classifier embedding must have {JINA_DIM} dimensions; "
                f"received shape {embedding.shape}"
            )
        return embedding

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    async def classify(self, query: str) -> Dict[str, Optional[str]]:
        """
        Classify a raw user query.

        Args:
            query : raw Persian (or mixed) user utterance

        Returns:
            {
              "type"       : "general"  — route to RAG pipeline
                           | "chitchat" — skip RAG, handle with polite deflection
              "scenario_id": "chitchat" | None
            }
        """
        detailed = await self._classify_detailed(query)
        return {
            "type": detailed["type"],
            "scenario_id": detailed["scenario_id"],
        }

    async def classify_detailed(self, query: str) -> Dict:
        """
        Extended version of classify() that also returns confidence scores.
        Use this for logging, debugging, or threshold tuning.

        Returns:
            {
              "type"            : "general" | "chitchat"
              "scenario_id"     : "chitchat" | None
              "class_id"        : 0 | 1
              "confidence"      : float  — probability of the predicted class
              "p_actionable"    : float  — probability of ACTIONABLE_INTENT
              "p_chitchat"      : float  — probability of CHIT-CHAT
              "route_to_rag"    : bool
            }
        """
        return await self._classify_detailed(query)

    async def _classify_detailed(self, query: str) -> Dict:
        started = time.perf_counter()
        if not query or not query.strip():
            result = {
                "type"        : "general",
                "scenario_id" : None,
                "class_id"    : LABEL_ACTIONABLE,
                "confidence"  : 1.0,
                "p_actionable": 1.0,
                "p_chitchat"  : 0.0,
                "route_to_rag": True,
                "preprocessed_query": "",
            }
            emit_pipeline_stage_lazy(lambda: PipelineStageResult(
                stage=PipelineStage.INTENT,
                input_data={"classifier_input": query},
                output_data=result,
                metrics={"effective_threshold": self.threshold},
                duration_ms=(time.perf_counter() - started) * 1000,
            ))
            return result

        preprocessed_query = normalize_persian_text(query)
        if not preprocessed_query:
            result = {
                "type": "general",
                "scenario_id": None,
                "class_id": LABEL_ACTIONABLE,
                "confidence": 1.0,
                "p_actionable": 1.0,
                "p_chitchat": 0.0,
                "route_to_rag": True,
                "preprocessed_query": "",
            }
            emit_pipeline_stage_lazy(lambda: PipelineStageResult(
                stage=PipelineStage.INTENT,
                input_data={"classifier_input": query},
                output_data=result,
                metrics={"effective_threshold": self.threshold},
                duration_ms=(time.perf_counter() - started) * 1000,
            ))
            return result
        embedding = await self._encode(preprocessed_query)
        if self.blocking_runner is not None:
            class_id, confidence, p_act, p_chat = (
                await self.blocking_runner.run(
                    self._classify_embedding, embedding
                )
            )
        else:
            class_id, confidence, p_act, p_chat = await asyncio.to_thread(
                self._classify_embedding, embedding
            )

        is_chitchat = class_id == LABEL_CHITCHAT
        result = {
            "type"        : "chitchat" if is_chitchat else "general",
            "scenario_id" : "chitchat" if is_chitchat else None,
            "class_id"    : class_id,
            "confidence"  : confidence,
            "p_actionable": p_act,
            "p_chitchat"  : p_chat,
            "route_to_rag": not is_chitchat,
            "preprocessed_query": preprocessed_query,
        }
        emit_pipeline_stage_lazy(lambda: PipelineStageResult(
            stage=PipelineStage.INTENT,
            input_data={"classifier_input": query},
            output_data=result,
            metrics={
                "effective_threshold": self.threshold,
                "embedding_dimension": JINA_DIM,
                "embedding_policy": "classification",
            },
            duration_ms=(time.perf_counter() - started) * 1000,
        ))
        return result

    def _classify_embedding(self, embedding):
        """Run the synchronous Torch forward pass outside the event loop."""
        with self._inference_lock:
            x = (
                torch.tensor(embedding, dtype=torch.float32)
                .to(self.device)
                .unsqueeze(0)
            )
            with torch.no_grad():
                logits = self.classifier(x)
                probs = torch.softmax(logits, dim=1).squeeze()
            class_id = (
                LABEL_CHITCHAT
                if float(probs[LABEL_CHITCHAT].item()) >= self.threshold
                else LABEL_ACTIONABLE
            )
            return (
                class_id,
                float(probs[class_id].item()),
                float(probs[LABEL_ACTIONABLE].item()),
                float(probs[LABEL_CHITCHAT].item()),
            )
