"""Convert, validate, then optionally publish and ingest one new knowledge source."""
from __future__ import annotations

import argparse
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from new_architecture.knowledge_sources import discover_chunk_files


class CommandFailure(RuntimeError):
    """Only fixed, non-sensitive subprocess diagnostics may reach the console."""


def checked_command(command):
    # Keep raw stderr private: parser errors can include source rows or secrets.
    with tempfile.TemporaryFile(mode="w+b") as errors:
        result = subprocess.run(command, cwd=REPO, stdout=subprocess.DEVNULL,
                                stderr=errors)
        if not result.returncode:
            return
        reason = "Subprocess failed; raw diagnostics suppressed to protect source data and credentials."
        if len(command) > 1 and command[1] == str(REPO / "hihelp_knowledge_changer.py"):
            errors.seek(0, os.SEEK_END)
            errors.seek(max(0, errors.tell() - 65536))
            lines = errors.read().decode("utf-8", errors="replace").splitlines()
            # Match entire terminal lines, never forward arbitrary exception text.
            messages = {
                "ValueError: Knowledge CSV is missing required columns":
                    "CSV is missing one or more exact required column names. "
                    "See docs/ingestion/ADD_KNOWLEDGE_SOURCE.md for the original schema.",
                "ValueError: Knowledge CSV contains no valid question/answer rows":
                    "CSV contains no valid question/answer rows.",
            }
            if lines:
                reason = messages.get(lines[-1], reason)
        raise CommandFailure(reason)


def validate(root, name):
    document = root / "DOCUMENTS" / f"{name}.csv"
    folder = root / "CHUNKS" / name
    chunks = discover_chunk_files(folder)
    if not document.is_file() or not document.stat().st_size or not chunks:
        raise ValueError("Converter did not produce a nonempty document and chunks")
    expected = [folder / f"{name}_{i}.txt" for i in range(len(chunks))]
    if list(chunks) != expected or set(folder.iterdir()) != set(chunks):
        raise ValueError("Converter produced invalid numbered chunks")
    if any(not chunk.read_text(encoding="utf-8").strip() for chunk in chunks):
        raise ValueError("Converter produced empty chunks")
    return document, chunks


def refuse_destinations(root, name):
    docs = root / "DOCUMENTS"
    if (docs.exists() and any(p.stem == name for p in docs.iterdir())) or os.path.lexists(root / "CHUNKS" / name):
        raise FileExistsError("Source destination already exists; replacement is forbidden")
    for path in (root, docs, root / "CHUNKS"):
        if path.is_symlink():
            raise ValueError("Shared output directories must not be symlinks")


def publish(root, name, document, chunks):
    refuse_destinations(root, name)
    (root / "DOCUMENTS").mkdir(parents=True, exist_ok=True)
    (root / "CHUNKS").mkdir(parents=True, exist_ok=True)
    folder = root / "CHUNKS" / name
    folder.mkdir()  # exclusive source reservation; never remove partial publication
    for source, destination in [(document, root / "DOCUMENTS" / document.name)] + [
            (p, folder / p.name) for p in chunks]:
        with source.open("rb") as src, destination.open("xb") as dst:
            shutil.copyfileobj(src, dst)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-name", required=True)
    parser.add_argument("--output-root", type=Path, default=REPO / "data_insertion_chunks")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    name = args.source_name
    if not name or name.startswith(".") or Path(name).name != name or "\\" in name:
        parser.error("Invalid source name")
    if not args.source.is_absolute() or not args.output_root.is_absolute():
        parser.error("Source and output root must be absolute paths")
    publishing = False
    phase = "destination checks"
    try:
        refuse_destinations(args.output_root, name)
        with tempfile.TemporaryDirectory(prefix="ragbot-convert-") as temp:
            staging = Path(temp)
            phase = "conversion"
            checked_command([sys.executable, str(REPO / "hihelp_knowledge_changer.py"),
                             "--source", str(args.source), "--source-name", name,
                             "--output-root", str(staging)])
            phase = "staging validation"
            document, chunks = validate(staging, name)
            if not args.apply:
                print(f"Dry run validated {len(chunks)} chunks. No files published; no services contacted.")
                return 0
            # Local cooperating runners serialize publication. PostgreSQL advisory
            # locks in the importer serialize same-source service operations across hosts.
            args.output_root.mkdir(parents=True, exist_ok=True)
            with (args.output_root / ".add-knowledge.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                refuse_destinations(args.output_root, name)
                importer = [sys.executable, str(REPO / "new_architecture/data_insertion_with_api.py"),
                            "--source-name", name, "--insert-only", "--yes"]
                phase = "insert-only preflight"
                checked_command(importer + ["--data-root", str(staging), "--preflight-only"])
                phase = "exclusive file publication"
                publishing = True
                publish(args.output_root, name, document, chunks)
                phase = "insert-only ingestion"
                checked_command(importer + ["--data-root", str(args.output_root)])
        print("Source published and insert-only ingestion verified.")
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(f"Add-source operation failed during {phase}; no existing data was replaced or deleted.")
        if isinstance(exc, CommandFailure):
            print(str(exc))
        if publishing:
            print("Partial NEW files, PostgreSQL records, MinIO objects or Qdrant vectors may remain. "
                  "Inspect state before retrying; no cross-store transaction or automatic cleanup is provided.")
        else:
            print("No source files were published. Check input, destination and preflight prerequisites.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
