"""Pure filesystem rules for discovering ingestible knowledge sources."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


HIDDEN_OR_PLACEHOLDER_NAMES = {".gitkeep", ".keep", ".placeholder"}
CHUNK_INDEX_PATTERN = re.compile(r"_(\d+)$")


@dataclass(frozen=True)
class KnowledgeSource:
    file_path: Path
    title: str
    chunk_dir: Path
    chunk_files: tuple[Path, ...]


def is_ignored_path(path: Path) -> bool:
    """Return true for hidden, placeholder, non-file, or empty entries."""
    return (
        not path.is_file()
        or path.name in HIDDEN_OR_PLACEHOLDER_NAMES
        or path.name.startswith(".")
        or not path.stem.strip()
        or path.stat().st_size == 0
    )


def discover_chunk_files(chunk_dir: Path) -> tuple[Path, ...]:
    """Return non-empty, numbered text chunks in deterministic order."""
    if not chunk_dir.is_dir():
        return ()

    indexed: list[tuple[int, Path]] = []
    for path in chunk_dir.iterdir():
        if is_ignored_path(path) or path.suffix.lower() != ".txt":
            continue
        match = CHUNK_INDEX_PATTERN.search(path.stem)
        if match is None:
            continue
        indexed.append((int(match.group(1)), path))
    indexed.sort(key=lambda item: (item[0], item[1].name))
    return tuple(path for _, path in indexed)


def discover_knowledge_sources(
    documents_dir: str | Path,
    chunks_root: str | Path,
) -> tuple[KnowledgeSource, ...]:
    """Find source files that have at least one valid generated chunk."""
    documents_path = Path(documents_dir)
    chunks_path = Path(chunks_root)
    if not documents_path.is_dir() or not chunks_path.is_dir():
        return ()

    sources: list[KnowledgeSource] = []
    for file_path in sorted(documents_path.iterdir(), key=lambda path: path.name):
        if is_ignored_path(file_path):
            continue
        title = file_path.stem.strip()
        chunk_dir = chunks_path / title
        chunk_files = discover_chunk_files(chunk_dir)
        if not chunk_files:
            continue
        sources.append(
            KnowledgeSource(
                file_path=file_path,
                title=title,
                chunk_dir=chunk_dir,
                chunk_files=chunk_files,
            )
        )
    return tuple(sources)


def count_generated_knowledge(root: str | Path) -> dict[str, int]:
    """Count valid source documents and chunks without reading their content."""
    root_path = Path(root)
    documents_dir = root_path / "DOCUMENTS"
    chunks_root = root_path / "CHUNKS"
    source_files = (
        [path for path in documents_dir.iterdir() if not is_ignored_path(path)]
        if documents_dir.is_dir()
        else []
    )
    chunk_files: list[Path] = []
    if chunks_root.is_dir():
        for chunk_dir in chunks_root.iterdir():
            chunk_files.extend(discover_chunk_files(chunk_dir))
    return {"source_documents": len(source_files), "chunks": len(chunk_files)}


def build_datasource_listing(document_titles, category_resolver) -> dict:
    """Build the chat API payload with defensive blank/duplicate filtering."""
    titles = list(dict.fromkeys(
        str(title).strip() for title in document_titles if str(title).strip()
    ))
    documents = [
        {"name": title, "category": category_resolver(title)}
        for title in titles
    ]
    return {
        "documents": documents,
        "count": len(documents),
        "categories": sorted({item["category"] for item in documents}),
    }
