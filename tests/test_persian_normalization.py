from __future__ import annotations

import time
import unittest

from utils.persian_normalization import ZWNJ, normalize_persian_text


ACCOUNT_OBJECT_VARIANTS = (
    "میشه اسم حساب هارو بگی",
    "میشه اسم حساب ها رو بگی",
    f"میشه اسم حساب{ZWNJ}ها رو بگی",
    "میشه اسم حسابها رو بگی",
    f"میشه اسم حساب{ZWNJ}ها را بگی",
    "میشه اسم حساب ها را بگی",
    f"می{ZWNJ}شه اسم حساب{ZWNJ}ها رو بگی",
    "می شه اسم حساب ها رو بگی",
)


class PersianNormalizationTests(unittest.TestCase):
    def test_account_plural_object_variants_share_one_representation(self):
        normalized = {normalize_persian_text(text) for text in ACCOUNT_OBJECT_VARIANTS}
        self.assertEqual(normalized, {"میشه اسم حساب هارو بگی"})

    def test_short_plural_naming_questions_share_one_representation(self):
        variants = (
            f"اسم حساب{ZWNJ}ها چیست؟",
            "اسم حساب ها چیست؟",
            "اسم حسابها چیست?",
        )
        self.assertEqual(
            {normalize_persian_text(text) for text in variants},
            {"اسم حساب هارو بگی"},
        )

    def test_arabic_and_persian_character_variants_are_equal(self):
        self.assertEqual(normalize_persian_text("ميشه"), "میشه")
        self.assertEqual(normalize_persian_text("كارت"), "کارت")
        self.assertEqual(normalize_persian_text("على"), "علی")

    def test_unicode_spaces_and_invisible_joiners_are_canonical(self):
        variants = (
            "  میشه\u00a0اسم   حساب ها رو بگی  ",
            "میشه اسم حساب\u200dها رو بگی",
            "میشه اسم حساب\u200cها رو بگی",
        )
        self.assertEqual(
            {normalize_persian_text(value) for value in variants},
            {"میشه اسم حساب هارو بگی"},
        )

    def test_plural_and_plural_ye_variants_use_zwnj_without_object_marker(self):
        self.assertEqual(normalize_persian_text("حساب ها"), f"حساب{ZWNJ}ها")
        self.assertEqual(normalize_persian_text("حسابها"), f"حساب{ZWNJ}ها")
        self.assertEqual(normalize_persian_text("حساب های بانکی"), f"حساب{ZWNJ}های بانکی")
        self.assertEqual(normalize_persian_text("حسابهای بانکی"), f"حساب{ZWNJ}های بانکی")

    def test_colloquial_object_marker_is_not_rewritten_globally(self):
        self.assertEqual(normalize_persian_text("تنها رو بگو"), "تنها رو بگو")
        self.assertEqual(normalize_persian_text("کارت رو بگو"), "کارت رو بگو")
        self.assertEqual(normalize_persian_text("رها رو صدا کن"), "رها رو صدا کن")

    def test_structured_values_are_preserved(self):
        values = (
            "6037 9912 3456 7890",
            "+98-21-23350",
            "https://example.com/a?x=1&y=2",
            "Hibank-ACC-001",
        )
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(normalize_persian_text(value), value)

    def test_false_equivalence_entities_remain_distinct(self):
        pairs = (
            ("حساب بانکی", f"حساب کاربری گیت{ZWNJ}هاب"),
            ("کارت بانکی", "کارت گرافیک"),
            ("رمز Hibank", f"رمز وای{ZWNJ}فای"),
        )
        for banking, unrelated in pairs:
            with self.subTest(banking=banking, unrelated=unrelated):
                self.assertNotEqual(
                    normalize_persian_text(banking),
                    normalize_persian_text(unrelated),
                )

    def test_normalization_is_idempotent(self):
        for value in ACCOUNT_OBJECT_VARIANTS:
            normalized = normalize_persian_text(value)
            self.assertEqual(normalize_persian_text(normalized), normalized)

    def test_normalizer_overhead_is_cpu_cheap(self):
        started = time.perf_counter()
        for _ in range(20_000):
            normalize_persian_text("  مي شه اسم حساب\u00a0ها رو بگی؟  ")
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
