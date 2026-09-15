"""Process-local lifecycle for the reusable RagBot HTTP client."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any


class WorkerRuntimeInitializationError(RuntimeError):
    """Content-free initialization failure safe for Celery logs."""

    def __init__(self, error_code: str):
        self.error_code = error_code
        super().__init__(f"evaluation worker runtime initialization failed: {error_code}")


def _default_client_factory() -> AbstractAsyncContextManager:
    from ..clients.ragbot import RagBotEvaluationClient
    from ..config import get_settings

    settings = get_settings()
    return RagBotEvaluationClient(
        base_url=settings.ragbot_base_url,
        timeout_seconds=settings.ragbot_http_timeout_seconds,
    )


class WorkerProcessRuntime:
    """Own one event loop and one HTTP client for a worker process."""

    def __init__(
        self,
        *,
        client_factory: Callable[[], AbstractAsyncContextManager] | None = None,
    ) -> None:
        self._client_factory = client_factory or _default_client_factory
        self._lock = threading.RLock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client_context: AbstractAsyncContextManager | None = None
        self._ragbot_client: Any = None
        self._closed = False

    @property
    def initialized(self) -> bool:
        return self._ragbot_client is not None

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._closed:
            raise RuntimeError("evaluation worker runtime is closed")
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
        return self._loop

    def _ensure_client(self) -> Any:
        if self._ragbot_client is not None:
            return self._ragbot_client
        loop = self._ensure_loop()
        context = self._client_factory()
        try:
            client = loop.run_until_complete(context.__aenter__())
        except BaseException:
            self._client_context = None
            self._ragbot_client = None
            raise WorkerRuntimeInitializationError(
                "EVALUATION_WORKER_INIT_FAILED"
            ) from None
        self._client_context = context
        self._ragbot_client = client
        return client

    def run_with_client(
        self,
        operation: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """Run one task on the persistent loop with the shared HTTP client."""

        with self._lock:
            client = self._ensure_client()
            return self._ensure_loop().run_until_complete(operation(client))

    def run_maintenance(self, awaitable: Awaitable[Any]) -> Any:
        """Run failure persistence on the same loop, even before init succeeds."""

        with self._lock:
            return self._ensure_loop().run_until_complete(awaitable)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            loop = self._loop
            context = self._client_context
            self._client_context = None
            self._ragbot_client = None
            if loop is not None and context is not None:
                try:
                    loop.run_until_complete(context.__aexit__(None, None, None))
                except Exception:
                    pass
            if loop is not None:
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:
                    pass
                loop.close()
            self._loop = None
            self._closed = True


_singleton_lock = threading.Lock()
_worker_runtime: WorkerProcessRuntime | None = None


def get_worker_runtime() -> WorkerProcessRuntime:
    global _worker_runtime
    with _singleton_lock:
        if _worker_runtime is None:
            _worker_runtime = WorkerProcessRuntime()
        return _worker_runtime


def close_worker_runtime() -> None:
    global _worker_runtime
    with _singleton_lock:
        runtime = _worker_runtime
        _worker_runtime = None
    if runtime is not None:
        runtime.close()
