from __future__ import annotations

import asyncio
import csv
import hashlib
import inspect
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch

from intent_classifier import (
    JINA_DIM,
    LABEL_ACTIONABLE,
    LABEL_CHITCHAT,
    IntentClassifier,
    _GuardrailNet,
)
from training.intent_classifier.common import (
    LABEL_MAP,
    normalize_persian,
    read_csv,
    read_faqs,
)
from training.intent_classifier.modeling import load_compatible_checkpoint, sha256_file


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "training/intent_classifier/data"
FAQ_DIR = ROOT / "data_insertion_chunks/CHUNKS/General_FAQ"
OLD_CHECKPOINT = ROOT / "chitchat_guardrail.pt"
NEW_CHECKPOINT = ROOT / "chitchat_guardrail_finetuned.pt"
EXPECTED_OLD_SHA256 = "c1f55e9bd4c67764d10052ac45d8c34285329f56047bde7a48c0a7f6b8ae49cc"


class DatasetIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.master = read_csv(DATA / "intent_classifier_finetune.csv")
        cls.train = read_csv(DATA / "intent_classifier_train.csv")
        cls.validation = read_csv(DATA / "intent_classifier_validation.csv")
        cls.test = read_csv(DATA / "intent_classifier_test.csv")
        cls.adversarial = read_csv(DATA / "intent_classifier_adversarial_test.csv")
        cls.review = read_csv(DATA / "review_required.csv")
        cls.faqs, _ = read_faqs(FAQ_DIR)

    def test_labels_are_binary_and_mapping_is_fixed(self) -> None:
        self.assertEqual({int(row["label"]) for row in self.master}, {0, 1})
        self.assertEqual(LABEL_ACTIONABLE, 0)
        self.assertEqual(LABEL_CHITCHAT, 1)
        self.assertEqual(LABEL_MAP, {0: "ACTIONABLE_INTENT", 1: "CHIT-CHAT"})

    def test_text_is_never_null_or_empty(self) -> None:
        self.assertTrue(all(row["text"] and row["text"].strip() for row in self.master))

    def test_no_exact_duplicate_has_conflicting_labels(self) -> None:
        labels: dict[str, set[str]] = defaultdict(set)
        for row in self.master:
            labels[row["text"]].add(row["label"])
        self.assertFalse({text: value for text, value in labels.items() if len(value) > 1})

    def test_no_exact_duplicate_rows(self) -> None:
        texts = [row["text"] for row in self.master]
        self.assertEqual(len(texts), len(set(texts)))

    def test_source_and_family_groups_do_not_cross_splits(self) -> None:
        splits: dict[str, set[str]] = defaultdict(set)
        for row in self.master:
            group = row["source_question_id"] or row["generation_family"]
            splits[group].add(row["split"])
        self.assertFalse({group: value for group, value in splits.items() if len(value) > 1})

    def test_every_label_zero_row_references_real_faq(self) -> None:
        valid = {faq.source_question_id for faq in self.faqs}
        self.assertTrue(all(row["source_question_id"] in valid for row in self.master if int(row["label"]) == 0))

    def test_reported_banking_regressions_have_kb_answer_sources(self) -> None:
        blocked_card_sources = [
            faq for faq in self.faqs
            if "کارت" in normalize_persian(faq.question)
            and "مسدود" in normalize_persian(faq.question)
            and faq.answer.strip()
        ]
        card_delivery_sources = [
            faq for faq in self.faqs
            if "کارت" in normalize_persian(faq.question)
            and any(term in normalize_persian(faq.question) for term in ("ارسال", "دریافت"))
            and faq.answer.strip()
        ]
        self.assertTrue(blocked_card_sources)
        self.assertTrue(card_delivery_sources)

    def test_class_balance_is_within_five_percentage_points(self) -> None:
        banking = sum(int(row["label"]) == 0 for row in self.master)
        self.assertGreaterEqual(banking / len(self.master), 0.45)
        self.assertLessEqual(banking / len(self.master), 0.55)
        for rows in (self.train, self.validation, self.test):
            split_banking = sum(int(row["label"]) == 0 for row in rows)
            self.assertGreaterEqual(split_banking / len(rows), 0.45)
            self.assertLessEqual(split_banking / len(rows), 0.55)

    def test_split_files_exactly_partition_master(self) -> None:
        expected = {row["text"] for row in self.master}
        actual = {row["text"] for row in self.train + self.validation + self.test}
        self.assertEqual(expected, actual)
        self.assertEqual(len(self.master), len(self.train) + len(self.validation) + len(self.test))

    def test_every_example_type_is_represented_in_each_ordinary_split(self) -> None:
        expected = {row["example_type"] for row in self.master}
        for rows in (self.train, self.validation, self.test):
            self.assertEqual({row["example_type"] for row in rows}, expected)

    def test_adversarial_set_is_not_in_master_or_training(self) -> None:
        master = {normalize_persian(row["text"], punctuation=True) for row in self.master}
        adversarial = {normalize_persian(row["text"], punctuation=True) for row in self.adversarial}
        self.assertTrue(adversarial)
        self.assertFalse(master & adversarial)

    def test_review_required_is_excluded_and_captures_meta_conflict(self) -> None:
        master = {row["text"] for row in self.master}
        review = {row["text"] for row in self.review}
        self.assertTrue(review)
        self.assertFalse(master & review)
        self.assertEqual({row["review_reason"] for row in self.review}, {
            "source FAQ conflicts with the explicit rule that assistant/meta questions are label 1"
        })

    def test_master_has_no_grouped_train_test_leakage(self) -> None:
        train_groups = {row["source_question_id"] or row["generation_family"] for row in self.train}
        validation_groups = {row["source_question_id"] or row["generation_family"] for row in self.validation}
        test_groups = {row["source_question_id"] or row["generation_family"] for row in self.test}
        self.assertFalse(train_groups & validation_groups)
        self.assertFalse(train_groups & test_groups)
        self.assertFalse(validation_groups & test_groups)

    def test_reader_ignores_gitkeep_hidden_empty_and_temporary_files(self) -> None:
        valid = "question : پرسش آزمایشی؟\nanswer : پاسخ\nquestion category : عمومی. sub_category : آزمایش"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "valid.txt").write_text(valid, encoding="utf-8")
            (root / ".gitkeep").write_text("", encoding="utf-8")
            (root / ".hidden.txt").write_text(valid, encoding="utf-8")
            (root / "empty.txt").write_text("", encoding="utf-8")
            (root / "temporary.tmp").write_text(valid, encoding="utf-8")
            (root / "temporary.tmp.txt~").write_text(valid, encoding="utf-8")
            faqs, stats = read_faqs(root)
        self.assertEqual(len(faqs), 1)
        self.assertEqual(
            stats,
            {
                "hidden_ignored": 2,
                "empty_ignored": 1,
                "temporary_ignored": 2,
                "non_txt_ignored": 0,
            },
        )


class CheckpointCompatibilityTests(unittest.TestCase):
    class _InlineRunner:
        async def run(self, function, *args):
            return function(*args)

    def test_original_checkpoint_checksum_is_unchanged(self) -> None:
        self.assertEqual(sha256_file(OLD_CHECKPOINT), EXPECTED_OLD_SHA256)

    def test_application_default_selects_finetuned_checkpoint(self) -> None:
        parameters = inspect.signature(IntentClassifier.__init__).parameters
        default_path = parameters["classifier_model_path"].default
        self.assertEqual(default_path, "chitchat_guardrail_finetuned.pt")
        self.assertEqual(parameters["similarity_threshold"].default, 0.875)

    def test_probability_between_half_and_threshold_routes_to_banking(self) -> None:
        class FixedProbabilityNet(torch.nn.Module):
            def forward(self, features):
                probabilities = torch.tensor(
                    [[0.3643, 0.6357]], dtype=torch.float32,
                    device=features.device,
                ).repeat(features.shape[0], 1)
                return torch.log(probabilities)

        async def fake_embedding(_: str) -> list[float]:
            return np.zeros(JINA_DIM, dtype=np.float32).tolist()

        classifier = IntentClassifier(
            embedding_model=fake_embedding,
            classifier_model_path=None,
            similarity_threshold=0.875,
            device="cpu",
            blocking_runner=self._InlineRunner(),
        )
        classifier.classifier = FixedProbabilityNet()
        result = asyncio.run(
            classifier.classify_detailed("من کارتم مسدود شده باید چه کنم؟؟")
        )
        self.assertEqual(result["class_id"], LABEL_ACTIONABLE)
        self.assertTrue(result["route_to_rag"])
        self.assertAlmostEqual(result["p_chitchat"], 0.6357, places=4)

    def test_probability_above_threshold_routes_to_chitchat(self) -> None:
        class FixedProbabilityNet(torch.nn.Module):
            def forward(self, features):
                probabilities = torch.tensor(
                    [[0.0394, 0.9606]], dtype=torch.float32,
                    device=features.device,
                ).repeat(features.shape[0], 1)
                return torch.log(probabilities)

        async def fake_embedding(_: str) -> list[float]:
            return np.zeros(JINA_DIM, dtype=np.float32).tolist()

        classifier = IntentClassifier(
            embedding_model=fake_embedding,
            classifier_model_path=None,
            similarity_threshold=0.875,
            device="cpu",
            blocking_runner=self._InlineRunner(),
        )
        classifier.classifier = FixedProbabilityNet()
        result = asyncio.run(classifier.classify_detailed("سلام خوبی؟"))
        self.assertEqual(result["class_id"], LABEL_CHITCHAT)
        self.assertFalse(result["route_to_rag"])

    def test_current_architecture_loads_old_checkpoint_strictly(self) -> None:
        model, payload = load_compatible_checkpoint(OLD_CHECKPOINT, torch.device("cpu"))
        output = model(torch.zeros((3, JINA_DIM)))
        self.assertEqual(tuple(output.shape), (3, 2))
        self.assertEqual(payload["label_map"], LABEL_MAP)

    @unittest.skipUnless(NEW_CHECKPOINT.exists(), "fine-tuned checkpoint has not been produced")
    def test_current_architecture_loads_new_checkpoint_strictly(self) -> None:
        model, payload = load_compatible_checkpoint(NEW_CHECKPOINT, torch.device("cpu"))
        output = model(torch.zeros((3, JINA_DIM)))
        self.assertEqual(tuple(output.shape), (3, 2))
        self.assertEqual(payload["label_map"], LABEL_MAP)

    def test_old_checkpoint_runs_same_public_preprocessing_path(self) -> None:
        async def fake_embedding(_: str) -> list[float]:
            return np.zeros(JINA_DIM, dtype=np.float32).tolist()

        classifier = IntentClassifier(
            embedding_model=fake_embedding,
            scenarios_path=str(ROOT / "scenarios.json"),
            classifier_model_path=str(OLD_CHECKPOINT),
            device="cpu",
            blocking_runner=self._InlineRunner(),
        )
        result = asyncio.run(classifier.classify_detailed("سلام، تست سازگاری"))
        self.assertIn(result["class_id"], (0, 1))
        self.assertAlmostEqual(result["p_actionable"] + result["p_chitchat"], 1.0, places=5)

    @unittest.skipUnless(NEW_CHECKPOINT.exists(), "fine-tuned checkpoint has not been produced")
    def test_new_checkpoint_runs_same_public_preprocessing_path(self) -> None:
        async def fake_embedding(_: str) -> list[float]:
            return np.zeros(JINA_DIM, dtype=np.float32).tolist()

        classifier = IntentClassifier(
            embedding_model=fake_embedding,
            scenarios_path=str(ROOT / "scenarios.json"),
            classifier_model_path=str(NEW_CHECKPOINT),
            device="cpu",
            blocking_runner=self._InlineRunner(),
        )
        result = asyncio.run(classifier.classify_detailed("سلام، تست سازگاری"))
        self.assertIn(result["class_id"], (0, 1))
        self.assertEqual(tuple(classifier.classifier(torch.zeros((2, JINA_DIM))).shape), (2, 2))


if __name__ == "__main__":
    unittest.main()
