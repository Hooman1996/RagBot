"""Thread-safety adapters for shared synchronous service clients."""

from __future__ import annotations

import threading


class SerializedClient:
    """Serialize method calls when an SDK's thread-safety is unverified.

    The wrapped client remains process-scoped and reusable, but is never entered
    concurrently from FastAPI worker threads or ``asyncio.to_thread`` workers.
    """

    def __init__(self, client):
        self._client = client
        self._lock = threading.RLock()
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def __getattr__(self, name):
        attribute = getattr(self._client, name)
        if not callable(attribute):
            return attribute

        def serialized(*args, **kwargs):
            with self._lock:
                if self._closed and name != "close":
                    raise RuntimeError("client is closed")
                return attribute(*args, **kwargs)

        return serialized

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._client.close()
            self._closed = True
