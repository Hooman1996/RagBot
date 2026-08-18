"""Small thread-safe cache whose entries are valid only for a shared revision."""

from __future__ import annotations

import threading
from typing import Callable, Generic, Hashable, TypeVar


Key = TypeVar("Key", bound=Hashable)
Value = TypeVar("Value")


class RevisionAwareCache(Generic[Key, Value]):
    def __init__(self) -> None:
        self._entries: dict[Key, tuple[str, Value]] = {}
        self._lock = threading.RLock()

    def get_or_build(
        self,
        key: Key,
        revision: str | None,
        builder: Callable[[], Value],
    ) -> Value:
        # Without a shared revision, reuse would have no cross-process
        # correctness proof. Build from the authoritative source instead.
        if revision is None:
            return builder()
        with self._lock:
            cached = self._entries.get(key)
            if cached is None or cached[0] != revision:
                value = builder()
                self._entries[key] = (revision, value)
                return value
            return cached[1]

    def clear(self) -> int:
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            return count
