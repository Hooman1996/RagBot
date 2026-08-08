"""Convert a source FAQ CSV into one document manifest and numbered chunks."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from new_architecture.knowledge_sources import discover_chunk_files


load_dotenv()


def _clean_cell(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).replace("\u200c", " ").strip()


def _resolve_source_name(source_csv: Path, requested_name: str | None) -> str:
    source_name = (requested_name or source_csv.stem).strip()
    if not source_name or source_name.startswith("."):
        raise ValueError("Knowledge source name cannot be empty or hidden")
    if Path(source_name).name != source_name:
        raise ValueError("Knowledge source name must not contain path separators")
    return source_name


def generate_knowledge_files(
    source_csv: str | Path,
    output_root: str | Path,
    *,
    source_name: str | None = None,
) -> dict[str, object]:
    """Generate a clean, deterministic datasource from one non-empty CSV."""
    source_path = Path(source_csv)
    output_path = Path(output_root)
    if not source_path.is_file() or source_path.stat().st_size == 0:
        raise ValueError(f"Knowledge source is missing or empty: {source_path}")

    title = _resolve_source_name(source_path, source_name)
    data = pd.read_csv(source_path)
    required_columns = {
        "سوال استاندارد",
        "موضوع اصلی",
        "کلید کنترل تجمیع",
        "سوال شفاف‌سازی شده",
        "پاسخ",
    }
    missing = sorted(required_columns.difference(data.columns))
    if missing:
        raise ValueError("Knowledge CSV is missing required columns")

    documents_dir = output_path / "DOCUMENTS"
    chunks_dir = output_path / "CHUNKS" / title
    documents_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    # A shorter replacement dataset must not inherit old higher-numbered chunks.
    for old_chunk in discover_chunk_files(chunks_dir):
        old_chunk.unlink()

    rows: list[dict[str, str]] = []
    for _, source_row in data.iterrows():
        intended_question = _clean_cell(source_row["سوال شفاف‌سازی شده"])
        answer = _clean_cell(source_row["پاسخ"])
        category = _clean_cell(source_row["موضوع اصلی"])
        sub_category = _clean_cell(source_row["کلید کنترل تجمیع"])
        if not intended_question or not answer:
            continue
        rows.append(
            {
                "question_and_answer": (
                    f"question : {intended_question}\nanswer : {answer}"
                ),
                "category": category,
                "sub_category": sub_category,
            }
        )

    if not rows:
        raise ValueError("Knowledge CSV contains no valid question/answer rows")

    final_data = pd.DataFrame(
        rows,
        columns=["question_and_answer", "category", "sub_category"],
    )
    for index, row in final_data.iterrows():
        chunk = (
            f"{row['question_and_answer']}\n"
            f"question category : {row['category'].replace(chr(10), ' ')}. "
            f"sub_category : {row['sub_category'].replace(chr(10), ' ')}"
        )
        (chunks_dir / f"{title}_{index}.txt").write_text(
            chunk,
            encoding="utf-8",
            newline="",
        )

    document_path = documents_dir / f"{title}.csv"
    final_data.to_csv(document_path, index=False)
    return {
        "source_name": title,
        "document_path": str(document_path),
        "chunk_directory": str(chunks_dir),
        "chunk_count": len(final_data.index),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=os.getenv("KNOWLEDGE_BASE_CSV"),
        help="Source CSV (defaults to KNOWLEDGE_BASE_CSV)",
    )
    parser.add_argument(
        "--output-root",
        default=os.getenv("DATA_INSERTION_DIRECTORY"),
        help="Generated data root (defaults to DATA_INSERTION_DIRECTORY)",
    )
    parser.add_argument(
        "--source-name",
        default=os.getenv("KNOWLEDGE_SOURCE_NAME"),
        help="Optional datasource name; defaults to the source filename stem",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not args.source or not args.output_root:
        raise SystemExit(
            "Both a source CSV and output root are required via arguments or environment"
        )
    result = generate_knowledge_files(
        args.source,
        args.output_root,
        source_name=args.source_name,
    )
    print(
        f"Generated datasource {result['source_name']!r} with "
        f"{result['chunk_count']} chunks"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
