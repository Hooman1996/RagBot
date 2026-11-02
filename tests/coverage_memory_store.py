"""Dict-backed coverage store for synthetic tests only."""
from copy import deepcopy
from datetime import datetime
import hashlib
import secrets
import threading

from coverage_check import store as storage
from coverage_check.store import CHUNK_KEY, RUN_ID, STATES, StoreError, safe_file_name


class MemoryCheckStore:
    def __init__(self):
        self.runs, self.rows, self.chunks = {}, {}, {}
        self._results, self._suggestions = {}, {}
        self._lock = threading.Lock()
        self.closed = False

    def ensure_schema(self):
        pass

    def close(self):
        self.closed = True

    def _run(self, run_id):
        if not isinstance(run_id, str) or not RUN_ID.match(run_id) or run_id not in self.runs:
            raise StoreError("not_found")
        return self.runs[run_id]

    def create(self, *, owner_id, file_name, documents, settings, rows, prompt_version):
        run_id = "c_" + secrets.token_hex(16)
        meta = {"run_id": run_id, "created_at": storage.now(), "owner_id": owner_id,
                "file_name": safe_file_name(file_name), "documents": list(documents),
                "settings": dict(settings), "prompt_version": str(prompt_version),
                "state": "queued", "row_count": len(rows)}
        self.runs[run_id] = deepcopy(meta)
        self.rows[run_id] = {r["row"]: {"input": deepcopy(r), "result": None, "suggestion": None} for r in rows}
        self.chunks[run_id] = {}
        with self._lock:
            self._results[run_id] = {}
        return meta

    def meta(self, run_id):
        return deepcopy(self._run(run_id))

    def set_state(self, run_id, state):
        if state not in STATES:
            raise StoreError("invalid_state")
        self._run(run_id)["state"] = state
        return self.meta(run_id)

    def list(self, since: datetime | None = None):
        metas = [deepcopy(m) for m in self.runs.values() if since is None
                 or datetime.fromisoformat(m["created_at"]) >= since or m["state"] in {"queued", "running"}]
        return sorted(metas, key=lambda m: (m["created_at"], m["run_id"]), reverse=True)

    def delete(self, run_id):
        self._run(run_id)
        for mapping in (self.runs, self.rows, self.chunks):
            mapping.pop(run_id)
        with self._lock:
            self._results.pop(run_id, None)
            self._suggestions.pop(run_id, None)

    def inputs(self, run_id):
        self._run(run_id)
        return [deepcopy(r["input"]) for _, r in sorted(self.rows[run_id].items())]

    def _codes(self, run_id, cache, column, field):
        with self._lock:
            cached = cache.get(run_id)
            if cached is not None:
                return dict(cached)
        self._run(run_id)
        codes = {n: r[column][field] for n, r in self.rows[run_id].items() if r[column] is not None}
        with self._lock:
            cache.setdefault(run_id, codes)
            return dict(cache[run_id])

    def result_codes(self, run_id):
        return self._codes(run_id, self._results, "result", "result")

    def result(self, run_id, row):
        self._run(run_id)
        return deepcopy(self.rows[run_id].get(int(row), {}).get("result"))

    def write_result(self, run_id, row, data):
        self.result_codes(run_id)
        if int(row) not in self.rows[run_id]:
            raise StoreError("not_found")
        self.rows[run_id][int(row)]["result"] = deepcopy(data)
        with self._lock:
            self._results.setdefault(run_id, {})[int(row)] = data["result"]

    def write_texts(self, run_id, texts):
        self._run(run_id)
        keys = {}
        for chunk_id, text in texts.items():
            key = hashlib.sha256(str(text).encode("utf-8")).hexdigest()
            self.chunks[run_id].setdefault(key, str(text))
            keys[str(chunk_id)] = key
        return keys

    def chunk_text(self, run_id, key):
        if not isinstance(key, str) or not CHUNK_KEY.fullmatch(key):
            return None
        self._run(run_id)
        return self.chunks[run_id].get(key)

    def suggestion_statuses(self, run_id):
        return self._codes(run_id, self._suggestions, "suggestion", "status")

    def suggested_rows(self, run_id):
        return {row for row, status in self.suggestion_statuses(run_id).items() if status == "done"}

    def suggestion(self, run_id, row):
        self._run(run_id)
        return deepcopy(self.rows[run_id].get(int(row), {}).get("suggestion"))

    def write_suggestion(self, run_id, row, data):
        self.suggestion_statuses(run_id)
        if int(row) not in self.rows[run_id]:
            raise StoreError("not_found")
        self.rows[run_id][int(row)]["suggestion"] = deepcopy(data)
        with self._lock:
            self._suggestions.setdefault(run_id, {})[int(row)] = data["status"]

    def row_page(self, run_id, after_row, limit):
        return [deepcopy(record) for n, record in sorted(self.rows.get(run_id, {}).items()) if n > after_row][:limit]
