from __future__ import annotations

import asyncio
import hashlib
import unittest
from pathlib import Path

import numpy as np
import torch

from intent_classifier import (
    EXPECTED_ARCHITECTURE,
    EXPECTED_LABEL_MAP,
    JINA_DIM,
    IntentClassifier,
    _GuardrailNet,
)
from intent_classifier_factory import build_intent_classifier
from utils.tei_embedding_client import build_query_payload


ARTIFACT = Path(
    "training/artifacts/intent_guardrail_jina_retrieval_query_v1.pt"
)


async def fixed_embedding(_: str) -> list[float]:
    return np.linspace(-0.25, 0.25, JINA_DIM, dtype=np.float32).tolist()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def env_for(path: Path, sha256: str, threshold: float) -> dict[str, str]:
    return {
        "INTENT_CLASSIFIER_MODEL_PATH": str(path),
        "INTENT_CLASSIFIER_THRESHOLD": str(threshold),
        "INTENT_CLASSIFIER_DEVICE": "cpu",
        "INTENT_CLASSIFIER_REQUIRED": "true",
        "INTENT_CLASSIFIER_EXPECTED_SHA256": sha256,
    }


class InlineBlockingRunner:
    async def run(self, function, *args):
        return function(*args)


@unittest.skipUnless(ARTIFACT.exists(), "trained artifact is not present")
class DeterminismHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.checkpoint = torch.load(ARTIFACT, map_location="cpu", weights_only=True)
        cls.threshold = float(cls.checkpoint["selected_threshold"])
        cls.sha256 = sha256_file(ARTIFACT)

    def test_checkpoint_metadata_architecture_threshold_and_label_map(self) -> None:
        self.assertEqual(self.checkpoint["architecture"], EXPECTED_ARCHITECTURE)
        self.assertEqual(self.checkpoint["embedding_dimension"], JINA_DIM)
        self.assertEqual(self.checkpoint["embedding_role"], "retrieval_query")
        self.assertEqual(self.checkpoint["embedding_prompt_name"], "query")
        self.assertIs(self.checkpoint["embedding_normalize"], True)
        self.assertEqual(self.checkpoint["label_map"], EXPECTED_LABEL_MAP)
        self.assertRegex(self.checkpoint["dataset_fingerprint"], r"^[0-9a-f]{64}$")
        self.assertIn("embedding_model", self.checkpoint)
        self.assertIn("tei_endpoint_identity", self.checkpoint)
        self.assertIn("training_timestamp", self.checkpoint)
        model = _GuardrailNet()
        model.load_state_dict(self.checkpoint["model_state_dict"], strict=True)

    def test_shared_query_payload_contract(self) -> None:
        payload = build_query_payload("  سلام  ")
        self.assertEqual(payload["prompt_name"], "query")
        self.assertIs(payload["normalize"], True)

    def test_required_missing_checkpoint_fails(self) -> None:
        values = env_for(
            Path("training/artifacts/absent-intent-checkpoint.pt"),
            "0" * 64,
            self.threshold,
        )
        with self.assertRaises(FileNotFoundError):
            build_intent_classifier(embedding_model=fixed_embedding, environ=values)

    def test_required_wrong_sha_fails(self) -> None:
        values = env_for(ARTIFACT, "0" * 64, self.threshold)
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            build_intent_classifier(embedding_model=fixed_embedding, environ=values)

    def test_required_threshold_metadata_mismatch_fails(self) -> None:
        values = env_for(ARTIFACT, self.sha256, self.threshold - 0.01)
        with self.assertRaisesRegex(ValueError, "threshold does not match"):
            build_intent_classifier(embedding_model=fixed_embedding, environ=values)

    def test_direct_main_and_evaluation_factory_results_are_identical(self) -> None:
        values = env_for(ARTIFACT, self.sha256, self.threshold)
        blocking_runner = InlineBlockingRunner()
        direct = IntentClassifier(
            embedding_model=fixed_embedding,
            classifier_model_path=str(ARTIFACT),
            similarity_threshold=self.threshold,
            device="cpu",
            required=True,
            expected_sha256=self.sha256,
            blocking_runner=blocking_runner,
        )
        main_runtime = build_intent_classifier(
            embedding_model=fixed_embedding,
            blocking_runner=blocking_runner,
            environ=values,
        )
        evaluation_runtime = build_intent_classifier(
            embedding_model=fixed_embedding,
            blocking_runner=blocking_runner,
            environ=values,
        )

        async def classify_all():
            return [
                await classifier.classify_detailed("سلام")
                for classifier in (direct, main_runtime, evaluation_runtime)
            ]

        results = asyncio.run(classify_all())
        comparable_keys = (
            "class_id",
            "p_actionable",
            "p_chitchat",
            "type",
            "effective_threshold",
        )
        reference = {key: results[0][key] for key in comparable_keys}
        self.assertEqual(reference, {key: results[1][key] for key in comparable_keys})
        self.assertEqual(reference, {key: results[2][key] for key in comparable_keys})


if __name__ == "__main__":
    unittest.main()
