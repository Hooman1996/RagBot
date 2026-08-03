from __future__ import annotations

import csv
import io
import os
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from openpyxl import load_workbook

from mass_answer_files import (
    MassAnswerFileError,
    parse_mass_answer_file,
    read_upload_limited,
    write_safe_output,
)


class FakeUpload:
    def __init__(self, contents: bytes):
        self.stream = io.BytesIO(contents)

    async def read(self, size=-1):
        return self.stream.read(size)


def xlsx_bytes(frame: pd.DataFrame) -> bytes:
    stream = io.BytesIO()
    frame.to_excel(stream, index=False, engine="openpyxl")
    return stream.getvalue()


class MassAnswerUploadTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_size_limit_is_enforced_while_reading(self):
        upload = FakeUpload(b"a" * 11)
        with self.assertRaisesRegex(MassAnswerFileError, "size limit"):
            await read_upload_limited(upload, max_bytes=10)

    async def test_empty_upload_is_rejected(self):
        with self.assertRaisesRegex(MassAnswerFileError, "empty"):
            await read_upload_limited(FakeUpload(b""), max_bytes=10)


class MassAnswerParsingTests(unittest.TestCase):
    def parse_csv(self, text: str, *, name="sample.csv", max_rows=100):
        return parse_mass_answer_file(
            contents=text.encode("utf-8"), filename=name, max_rows=max_rows
        )

    def test_valid_utf8_persian_csv(self):
        parsed = self.parse_csv("سؤال,دسته\nچگونه کارت بگیرم؟,کارت\n")
        self.assertEqual(parsed.question_column, "سؤال")
        self.assertEqual(parsed.dataframe.iloc[0]["دسته"], "کارت")

    def test_utf8_bom_csv(self):
        parsed = parse_mass_answer_file(
            contents="question\nسلام\n".encode("utf-8-sig"),
            filename="bom.csv",
            max_rows=10,
        )
        self.assertEqual(parsed.dataframe.iloc[0]["question"], "سلام")

    def test_quoted_comma_and_multiline_cell(self):
        parsed = self.parse_csv('question,note\n"خط اول, ادامه\nخط دوم",ok\n')
        self.assertIn("\n", parsed.dataframe.iloc[0]["question"])
        self.assertIn(",", parsed.dataframe.iloc[0]["question"])

    def test_detects_semicolon_delimiter(self):
        parsed = self.parse_csv("question;kind\nپرسش;faq\n")
        self.assertEqual(list(parsed.dataframe.columns), ["question", "kind"])

    def test_valid_xlsx_uses_first_sheet_and_preserves_unicode(self):
        contents = xlsx_bytes(pd.DataFrame({"پرسش": ["وام چیست؟"], "n": [12]}))
        parsed = parse_mass_answer_file(
            contents=contents, filename="sample.xlsx", max_rows=10
        )
        self.assertEqual(parsed.output_extension, ".xlsx")
        self.assertEqual(parsed.dataframe.iloc[0]["پرسش"], "وام چیست؟")

    def test_committed_safe_fixtures_parse(self):
        fixture_dir = os.path.join(
            os.path.dirname(__file__), "fixtures", "mass_answer"
        )
        for filename in ("sample_persian.csv", "sample_persian.xlsx"):
            with self.subTest(filename=filename):
                with open(os.path.join(fixture_dir, filename), "rb") as stream:
                    parsed = parse_mass_answer_file(
                        contents=stream.read(), filename=filename, max_rows=10
                    )
                self.assertEqual(len(parsed.dataframe.index), 2)

    def test_missing_required_column(self):
        with self.assertRaisesRegex(MassAnswerFileError, "Required query"):
            self.parse_csv("title\nvalue\n")

    def test_empty_and_header_only_files(self):
        with self.assertRaises(MassAnswerFileError):
            parse_mass_answer_file(contents=b"", filename="empty.csv", max_rows=10)
        with self.assertRaisesRegex(MassAnswerFileError, "no data rows"):
            self.parse_csv("question\n")

    def test_invalid_extension(self):
        with self.assertRaisesRegex(MassAnswerFileError, "Unsupported"):
            parse_mass_answer_file(
                contents=b"question\nq", filename="input.txt", max_rows=10
            )

    def test_malformed_csv_and_excel(self):
        with self.assertRaises(MassAnswerFileError):
            self.parse_csv('question,note\n"unterminated,x\n')
        with self.assertRaisesRegex(MassAnswerFileError, "malformed"):
            parse_mass_answer_file(
                contents=b"not a workbook", filename="bad.xlsx", max_rows=10
            )

    def test_duplicate_and_ambiguous_columns(self):
        with self.assertRaisesRegex(MassAnswerFileError, "Duplicate"):
            self.parse_csv(" question ,question\na,b\n")
        with self.assertRaisesRegex(MassAnswerFileError, "more than one"):
            self.parse_csv("question,پرسش\na,b\n")

    def test_maximum_row_limit(self):
        with self.assertRaisesRegex(MassAnswerFileError, "row limit"):
            self.parse_csv("question\na\nb\n", max_rows=1)

    def test_blank_rows_are_preserved_for_per_row_classification(self):
        parsed = self.parse_csv("question,note\na,x\n,\nb,z\n")
        self.assertEqual(len(parsed.dataframe.index), 3)
        self.assertTrue(pd.isna(parsed.dataframe.iloc[1]["question"]))

    def test_reserved_output_column_is_rejected(self):
        with self.assertRaisesRegex(MassAnswerFileError, "reserved"):
            self.parse_csv("question,status\na,old\n")


class MassAnswerOutputTests(unittest.TestCase):
    def test_csv_has_bom_and_quotes_multiline_answers(self):
        frame = pd.DataFrame({"question": ["پرسش"], "Answer (پاسخ)": ["خط ۱\nخط ۲"]})
        path = write_safe_output(frame, extension=".csv")
        try:
            with open(path, "rb") as stream:
                contents = stream.read()
            self.assertTrue(contents.startswith(b"\xef\xbb\xbf"))
            rows = list(csv.reader(io.StringIO(contents.decode("utf-8-sig"))))
            self.assertEqual(rows[1][1], "خط ۱\nخط ۲")
        finally:
            os.remove(path)

    def test_xlsx_is_valid_and_formula_injection_is_neutralized(self):
        frame = pd.DataFrame(
            {"question": ["=1+1", "+cmd", "-2+3", "@SUM(A1)", "safe"]}
        )
        path = write_safe_output(frame, extension=".xlsx")
        try:
            workbook = load_workbook(path, data_only=False)
            values = [cell.value for cell in workbook.active["A"]][1:]
            self.assertEqual(
                values, ["'=1+1", "'+cmd", "'-2+3", "'@SUM(A1)", "safe"]
            )
        finally:
            os.remove(path)

    def test_failed_write_removes_partial_output(self):
        descriptor, path = tempfile.mkstemp(suffix=".xlsx")
        os.close(descriptor)
        frame = pd.DataFrame({"question": ["q"]})
        try:
            with patch.object(
                pd.DataFrame, "to_excel", side_effect=RuntimeError("write failed")
            ):
                with self.assertRaises(RuntimeError):
                    write_safe_output(frame, extension=".xlsx", output_path=path)
            self.assertFalse(os.path.exists(path))
        finally:
            if os.path.exists(path):
                os.remove(path)


if __name__ == "__main__":
    unittest.main()
