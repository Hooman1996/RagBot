"""Private per-run folders: meta.json, input.json, results/<row>.json, chunks/<sha256>.json and
suggestions/<row>.json."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

RUN_ID = re.compile(r"^c_[0-9a-f]{32}$")
CHUNK_KEY = re.compile(r"[0-9a-f]{64}")
STATES = ("queued", "running", "completed", "cancelled", "interrupted")


class StoreError(Exception):
    """A fixed error code for the API; never carries file contents."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def parse_csv(raw: bytes, max_rows: int, extra: str | None = None) -> list[dict]:
    """Rows of {row, id, question}, plus ``extra`` when named; every other column is dropped here."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise StoreError("invalid_csv_encoding") from None
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=",")
    try:
        header = next(reader, None)
        names = [str(name).strip().lower() for name in header or []]
        if "query" not in names:
            raise StoreError("missing_query_column")
        query_index = names.index("query")
        id_index = names.index("id") if "id" in names else None
        if extra is not None and extra not in names:
            raise StoreError(f"missing_{extra}_column")
        extra_index = names.index(extra) if extra is not None else None
        rows = []
        for record in reader:
            if not record or all(not cell.strip() for cell in record):
                continue
            if len(rows) >= max_rows:
                raise StoreError("too_many_rows")
            question = record[query_index] if query_index < len(record) else ""
            row_id = record[id_index] if id_index is not None and id_index < len(record) else ""
            row = {"row": len(rows) + 1, "id": row_id, "question": question}
            if extra_index is not None:
                row[extra] = record[extra_index] if extra_index < len(record) else ""
            rows.append(row)
    except csv.Error:
        raise StoreError("invalid_csv") from None
    if not rows:
        raise StoreError("empty_csv")
    return rows


def safe_file_name(name: str) -> str:
    base = PurePosixPath(str(name).replace("\\", "/")).name
    return "".join(ch for ch in base if ch.isprintable())[:120]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class CheckStore:
    def __init__(self, artifact_dir: Path):
        self.root = Path(artifact_dir) / "checks"
        self._lock = threading.Lock()
        self._results: dict[str, dict[int, str]] = {}
        self._suggestions: dict[str, dict[int, str]] = {}

    # Private files -------------------------------------------------
    def _mkdir(self, path: Path) -> None:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path, 0o700)

    def _write(self, path: Path, data) -> None:
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise

    @staticmethod
    def _read(path: Path):
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)

    def _run(self, run_id: str) -> Path:
        if not isinstance(run_id, str) or not RUN_ID.match(run_id):
            raise StoreError("not_found")
        path = self.root / run_id
        if not (path / "meta.json").is_file():
            raise StoreError("not_found")
        return path

    # Runs ----------------------------------------------------------
    def create(self, *, owner_id: int, file_name: str, documents: list[str],
               settings: dict, rows: list[dict], prompt_version: str) -> dict:
        self._mkdir(self.root.parent)
        self._mkdir(self.root)
        run_id = "c_" + secrets.token_hex(16)
        path = self.root / run_id
        self._mkdir(path)
        self._mkdir(path / "results")
        self._mkdir(path / "chunks")
        meta = {"run_id": run_id, "created_at": now(), "owner_id": owner_id,
                "file_name": safe_file_name(file_name), "documents": list(documents),
                "settings": dict(settings), "prompt_version": str(prompt_version),
                "state": "queued", "row_count": len(rows)}
        self._write(path / "input.json", rows)
        self._write(path / "meta.json", meta)
        with self._lock:
            self._results[run_id] = {}
        return meta

    def meta(self, run_id: str) -> dict:
        return self._read(self._run(run_id) / "meta.json")

    def set_state(self, run_id: str, state: str) -> dict:
        if state not in STATES:
            raise StoreError("invalid_state")
        meta = self.meta(run_id)
        meta["state"] = state
        self._write(self.root / run_id / "meta.json", meta)
        return meta

    def list(self) -> list[dict]:
        if not self.root.is_dir():
            return []
        metas = []
        for path in self.root.iterdir():
            if RUN_ID.match(path.name) and (path / "meta.json").is_file():
                metas.append(self._read(path / "meta.json"))
        return sorted(metas, key=lambda m: (m["created_at"], m["run_id"]), reverse=True)

    def delete(self, run_id: str) -> None:
        """Removes the run's folder and cached codes; a folder that is a symlink or outside the root is not_found."""
        path = self._run(run_id)
        if path.is_symlink() or path.resolve().parent != self.root.resolve():
            raise StoreError("not_found")
        shutil.rmtree(path)
        with self._lock:
            self._results.pop(run_id, None)
            self._suggestions.pop(run_id, None)

    def inputs(self, run_id: str) -> list[dict]:
        return self._read(self._run(run_id) / "input.json")

    # Results -------------------------------------------------------
    def result_codes(self, run_id: str) -> dict[int, str]:
        """Row number -> result for every finished row, cached after the first read."""
        with self._lock:
            cached = self._results.get(run_id)
            if cached is not None:
                return dict(cached)
        folder = self._run(run_id) / "results"
        codes = {}
        for path in folder.glob("*.json"):
            if path.stem.isdigit():
                codes[int(path.stem)] = self._read(path)["result"]
        with self._lock:
            self._results.setdefault(run_id, codes)
            return dict(self._results[run_id])

    def result(self, run_id: str, row: int) -> dict | None:
        path = self._run(run_id) / "results" / f"{int(row)}.json"
        return self._read(path) if path.is_file() else None

    def write_result(self, run_id: str, row: int, data: dict) -> None:
        self.result_codes(run_id)
        self._write(self._run(run_id) / "results" / f"{int(row)}.json", data)
        with self._lock:
            self._results.setdefault(run_id, {})[int(row)] = data["result"]

    # Chunk text -------------------------------------------------------
    def write_texts(self, run_id: str, texts: dict[str, str]) -> dict[str, str]:
        """Chunk id -> sha256; each distinct text is stored once per run."""
        folder = self._run(run_id) / "chunks"
        if not folder.is_dir():
            self._mkdir(folder)
        keys = {}
        for chunk_id, text in texts.items():
            key = hashlib.sha256(str(text).encode("utf-8")).hexdigest()
            path = folder / f"{key}.json"
            if not path.is_file():
                self._write(path, {"text": str(text)})
            keys[str(chunk_id)] = key
        return keys

    def chunk_text(self, run_id: str, key) -> str | None:
        """The stored text, or None for a key that is not 64 lowercase hex or a missing file."""
        if not isinstance(key, str) or not CHUNK_KEY.fullmatch(key):
            return None
        path = self._run(run_id) / "chunks" / f"{key}.json"
        return self._read(path)["text"] if path.is_file() else None

    # Suggestions -------------------------------------------------------
    def suggestion_statuses(self, run_id: str) -> dict[int, str]:
        """Row number -> stored suggestion status, cached after the first read."""
        with self._lock:
            cached = self._suggestions.get(run_id)
            if cached is not None:
                return dict(cached)
        folder = self._run(run_id) / "suggestions"
        statuses = {}
        if folder.is_dir():
            for path in folder.glob("*.json"):
                if path.stem.isdigit():
                    statuses[int(path.stem)] = self._read(path)["status"]
        with self._lock:
            self._suggestions.setdefault(run_id, statuses)
            return dict(self._suggestions[run_id])

    def suggested_rows(self, run_id: str) -> set[int]:
        """Rows with a done suggestion."""
        return {row for row, status in self.suggestion_statuses(run_id).items() if status == "done"}

    def suggestion(self, run_id: str, row: int) -> dict | None:
        path = self._run(run_id) / "suggestions" / f"{int(row)}.json"
        return self._read(path) if path.is_file() else None

    def write_suggestion(self, run_id: str, row: int, data: dict) -> None:
        """A new suggestion for a row replaces the old one."""
        self.suggestion_statuses(run_id)
        folder = self._run(run_id) / "suggestions"
        if not folder.is_dir():
            self._mkdir(folder)
        self._write(folder / f"{int(row)}.json", data)
        with self._lock:
            self._suggestions.setdefault(run_id, {})[int(row)] = data["status"]
