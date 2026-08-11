from __future__ import annotations

import asyncio
import importlib.util
import unittest
from pathlib import Path

import numpy as np
from parsivar import Normalizer

from training.intent_classifier.build_training_dataset import phrase_spacing_variants
from training.persian_normalization.build_kb_phrase_lexicon import build_lexicon
from utils.persian_normalization import normalize_persian_text
from utils.persian_query_normalizer import KB_PHRASE_NORMALIZER


ROOT = Path(__file__).resolve().parents[1]
FAQ_DIR = ROOT / "data_insertion_chunks/CHUNKS/General_FAQ"
_INTENT_SPEC = importlib.util.spec_from_file_location(
    "kb_phrase_application_intent_classifier", ROOT / "intent_classifier.py"
)
if _INTENT_SPEC is None or _INTENT_SPEC.loader is None:
    raise RuntimeError("Unable to load application intent classifier")
_INTENT_MODULE = importlib.util.module_from_spec(_INTENT_SPEC)
_INTENT_SPEC.loader.exec_module(_INTENT_MODULE)
IntentClassifier = _INTENT_MODULE.IntentClassifier
JINA_DIM = _INTENT_MODULE.JINA_DIM


class KBPhraseLexiconTests(unittest.TestCase):
    def test_current_kb_artifact_has_expected_gate_counts(self):
        artifact = build_lexicon(FAQ_DIR)
        self.assertEqual(artifact["statistics"]["valid_faq_files"], 1426)
        self.assertEqual(artifact["statistics"]["discovered_candidates"], 2610)
        self.assertEqual(artifact["statistics"]["accepted_phrases"], 100)
        self.assertEqual(artifact["statistics"]["rejected_candidates"], 2510)

    def test_requested_known_phrases_restore_to_space_form(self):
        groups = (
            ("احراز هویت", "احراز‌هویت", "احرازهویت", "احراز  هویت"),
            ("افتتاح حساب", "افتتاح‌حساب", "افتتاححساب"),
            ("شماره حساب", "شماره‌حساب", "شمارهحساب"),
            ("قرض الحسنه", "قرض‌الحسنه", "قرضالحسنه"),
        )
        for group in groups:
            with self.subTest(group=group):
                self.assertEqual(
                    {normalize_persian_text(value) for value in group},
                    {group[0]},
                )

    def test_phrase_lexicon_is_loaded_once_and_contains_no_answers(self):
        self.assertEqual(KB_PHRASE_NORMALIZER.phrase_count, 100)
        payload = KB_PHRASE_NORMALIZER.artifact_path.read_text(encoding="utf-8")
        self.assertNotIn('"answer"', payload)


class ParsivarBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parsivar = Normalizer()

    def test_parsivar_alone_does_not_restore_concatenated_phrases(self):
        self.assertEqual(self.parsivar.normalize("احرازهویت"), "احرازهویت")
        self.assertEqual(self.parsivar.normalize("افتتاححساب"), "افتتاححساب")
        self.assertEqual(self.parsivar.normalize("شمارهحساب"), "شمارهحساب")
        self.assertEqual(self.parsivar.normalize("سفرفصلی چیه"), "سفرفصلی چیه")

    def test_parsivar_plus_canonical_layer_restores_known_phrases(self):
        self.assertEqual(
            normalize_persian_text(self.parsivar.normalize("سفرفصلی چیه")),
            "سفر فصلی چیه",
        )


class IntentRoutingOrthographyTests(unittest.TestCase):
    class InlineRunner:
        async def run(self, function, *args):
            return function(*args)

    def test_travel_spacing_variants_have_identical_classifier_input_and_route(self):
        encoded: list[str] = []

        async def fake_embedding(text: str):
            encoded.append(text)
            return np.zeros(JINA_DIM, dtype=np.float32)

        classifier = IntentClassifier(
            embedding_model=fake_embedding,
            classifier_model_path=None,
            device="cpu",
            blocking_runner=self.InlineRunner(),
        )
        spaced = asyncio.run(classifier.classify_detailed("سفر فصلی چیه"))
        compact = asyncio.run(classifier.classify_detailed("سفرفصلی چیه"))
        self.assertEqual(encoded, ["سفر فصلی چیه", "سفر فصلی چیه"])
        self.assertEqual(spaced["preprocessed_query"], compact["preprocessed_query"])
        self.assertEqual(spaced["type"], compact["type"])

    def test_training_generator_covers_all_boundary_error_forms(self):
        variants = phrase_spacing_variants(
            "درباره هوش مصنوعی توضیح بده", "هوش مصنوعی"
        )
        self.assertEqual(
            set(variants),
            {
                "درباره هوشمصنوعی توضیح بده",
                "درباره هوش‌مصنوعی توضیح بده",
                "درباره هوش  مصنوعی توضیح بده",
            },
        )


class SemanticBoundaryTests(unittest.TestCase):
    def test_unrelated_entities_remain_distinct(self):
        pairs = (
            ("حساب بانکی", "حساب کاربری گیت‌هاب"),
            ("کارت بانکی", "کارت گرافیک"),
            ("رمز Hibank", "رمز وای‌فای"),
        )
        for banking, unrelated in pairs:
            with self.subTest(banking=banking, unrelated=unrelated):
                self.assertNotEqual(
                    normalize_persian_text(banking),
                    normalize_persian_text(unrelated),
                )

    def test_unknown_compound_is_not_segmented(self):
        self.assertEqual(normalize_persian_text("کتابخانهکودک"), "کتابخانهکودک")


if __name__ == "__main__":
    unittest.main()
