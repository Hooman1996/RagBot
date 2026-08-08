from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from hihelp_knowledge_changer import generate_knowledge_files
from new_architecture.knowledge_sources import (
    build_datasource_listing,
    discover_knowledge_sources,
)


class KnowledgeSourceDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name) / "data"
        self.documents = self.root / "DOCUMENTS"
        self.chunks = self.root / "CHUNKS"
        self.documents.mkdir(parents=True)
        self.chunks.mkdir()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_empty_documents_directory_returns_zero_datasources(self):
        self.assertEqual(
            discover_knowledge_sources(self.documents, self.chunks), ()
        )

    def test_documents_gitkeep_returns_zero_datasources(self):
        (self.documents / ".gitkeep").write_text("\n")
        self.assertEqual(
            discover_knowledge_sources(self.documents, self.chunks), ()
        )

    def test_chunks_gitkeep_only_returns_zero_datasources(self):
        (self.documents / "General_FAQ.csv").write_text("header\nvalue\n")
        chunk_dir = self.chunks / "General_FAQ"
        chunk_dir.mkdir()
        (chunk_dir / ".gitkeep").write_text("\n")
        self.assertEqual(
            discover_knowledge_sources(self.documents, self.chunks), ()
        )

    def test_empty_source_file_returns_zero_datasources(self):
        (self.documents / "empty.csv").touch()
        (self.chunks / "empty").mkdir()
        (self.chunks / "empty" / "empty_0.txt").write_text("chunk")
        self.assertEqual(
            discover_knowledge_sources(self.documents, self.chunks), ()
        )

    def test_one_valid_source_produces_exactly_one_datasource(self):
        (self.documents / "current.csv").write_text("header\nvalue\n")
        (self.documents / ".gitkeep").write_text("\n")
        chunk_dir = self.chunks / "current"
        chunk_dir.mkdir()
        (chunk_dir / "current_0.txt").write_text("knowledge")
        (chunk_dir / ".gitkeep").write_text("\n")

        sources = discover_knowledge_sources(self.documents, self.chunks)

        self.assertEqual([source.title for source in sources], ["current"])
        self.assertEqual(
            [path.name for path in sources[0].chunk_files],
            ["current_0.txt"],
        )

    def test_empty_api_listing_is_an_empty_array_not_an_error(self):
        payload = build_datasource_listing([], lambda _title: "category")
        self.assertEqual(
            payload,
            {"documents": [], "count": 0, "categories": []},
        )

    def test_api_listing_never_returns_blank_or_duplicate_names(self):
        payload = build_datasource_listing(
            ["", "  ", "current", "current"],
            lambda _title: "category",
        )
        self.assertEqual(
            payload,
            {
                "documents": [{"name": "current", "category": "category"}],
                "count": 1,
                "categories": ["category"],
            },
        )

    def test_generator_uses_input_stem_and_removes_old_chunks(self):
        source = Path(self.temporary_directory.name) / "current_source.csv"
        dataframe = pd.DataFrame(
            [
                {
                    "سوال استاندارد": "q1",
                    "موضوع اصلی": "category",
                    "کلید کنترل تجمیع": "sub",
                    "سوال شفاف‌سازی شده": "question one",
                    "پاسخ": "answer one",
                },
                {
                    "سوال استاندارد": "q2",
                    "موضوع اصلی": "category",
                    "کلید کنترل تجمیع": "sub",
                    "سوال شفاف‌سازی شده": "question two",
                    "پاسخ": "answer two",
                },
            ]
        )
        dataframe.to_csv(source, index=False)
        stale_dir = self.chunks / "current_source"
        stale_dir.mkdir()
        (stale_dir / "current_source_99.txt").write_text("stale")

        result = generate_knowledge_files(source, self.root)

        self.assertEqual(result["source_name"], "current_source")
        self.assertEqual(result["chunk_count"], 2)
        self.assertFalse((stale_dir / "current_source_99.txt").exists())
        sources = discover_knowledge_sources(self.documents, self.chunks)
        self.assertEqual([item.title for item in sources], ["current_source"])


if __name__ == "__main__":
    unittest.main()
