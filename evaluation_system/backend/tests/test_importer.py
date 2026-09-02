from __future__ import annotations

import importlib.util
import io
import unittest
from datetime import datetime

from evaluation_system.backend.app.services.importer import (
    DatasetImportError,
    parse_dataset_file,
    parse_manual_dataset,
)


class ImporterTests(unittest.TestCase):
    def parse_csv(self, body: str):
        return parse_dataset_file(
            filename="input.csv", content=body.encode("utf-8"),
            dataset_type="PIPELINE_INSPECTION", max_rows=100,
        )

    def test_query_only_rows_become_unique_synthetic_sessions(self):
        parsed = self.parse_csv("query\nاول\nدوم\n")
        self.assertEqual(parsed.session_count, 2)
        self.assertTrue(all(item.synthetic_session for item in parsed.sessions))
        self.assertNotEqual(
            parsed.sessions[0].synthetic_label,
            parsed.sessions[1].synthetic_label,
        )

    def test_session_grouping_sorts_timestamp_then_source_row(self):
        parsed = self.parse_csv(
            "query,session_id,time\n"
            "سوم,42,2026-01-02T00:00:00Z\n"
            "اول,42,2026-01-01T00:00:00Z\n"
            "دوم,42,2026-01-01T00:00:00Z\n"
        )
        self.assertEqual(parsed.session_count, 1)
        self.assertEqual([item.query for item in parsed.sessions[0].turns], ["اول", "دوم", "سوم"])
        self.assertEqual([item.turn_index for item in parsed.sessions[0].turns], [1, 2, 3])

    def test_missing_or_invalid_timestamp_preserves_source_order_and_warns(self):
        parsed = self.parse_csv(
            "query,session_id,time\nاول,s,2026-01-02T00:00:00Z\nدوم,s,invalid\nسوم,s,\n"
        )
        self.assertEqual([item.query for item in parsed.sessions[0].turns], ["اول", "دوم", "سوم"])
        codes = {issue.code for issue in parsed.issues}
        self.assertIn("INVALID_TIMESTAMP", codes)
        self.assertIn("INCOMPLETE_SESSION_TIMESTAMPS", codes)

    def test_empty_query_is_accounted_not_silently_dropped(self):
        parsed = self.parse_csv("query,session_id\n,s\nvalid,s\n")
        self.assertEqual(parsed.row_count, 2)
        self.assertEqual(parsed.valid_row_count, 1)
        self.assertEqual(parsed.invalid_row_count, 1)
        self.assertEqual(parsed.issues[0].code, "EMPTY_QUERY")

    def test_nan_like_blank_session_is_missing(self):
        parsed = self.parse_csv("query,session_id\na,\nb,   \nc,NaN\n")
        self.assertEqual(parsed.session_count, 3)

    def test_manual_queries_are_one_ordered_session(self):
        parsed = parse_manual_dataset(["Q1", "Q2", "Q3"])
        self.assertEqual(parsed.session_count, 1)
        self.assertEqual([turn.query for turn in parsed.sessions[0].turns], ["Q1", "Q2", "Q3"])

    def test_missing_query_column_is_rejected(self):
        with self.assertRaises(DatasetImportError) as caught:
            self.parse_csv("question\nhello\n")
        self.assertEqual(caught.exception.code, "MISSING_QUERY_COLUMN")

    @unittest.skipUnless(importlib.util.find_spec("openpyxl"), "openpyxl is not installed")
    def test_xlsx_import(self):
        from openpyxl import Workbook
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["query", "session_id", "time"])
        sheet.append(["Q2", "x", datetime(2026, 1, 2)])
        sheet.append(["Q1", "x", datetime(2026, 1, 1)])
        stream = io.BytesIO(); workbook.save(stream)
        parsed = parse_dataset_file(
            filename="input.xlsx", content=stream.getvalue(),
            dataset_type="PIPELINE_INSPECTION", max_rows=100,
        )
        self.assertEqual([turn.query for turn in parsed.sessions[0].turns], ["Q1", "Q2"])


if __name__ == "__main__":
    unittest.main()
